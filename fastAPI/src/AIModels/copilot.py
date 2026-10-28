"""Local Copilot authentication, streaming, and an optional diagnostic probe."""

import argparse
import asyncio
import json
import logging
import os
import shutil
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from copilot import (
    CopilotClient,
    CopilotSession,
    PermissionRequest,
    RuntimeConnection,
    ToolSet,
)
from copilot.client import JsonRpcError, ProcessExitedError
from copilot.rpc import PermissionDecisionReject
from copilot.session import PermissionInvocation
from copilot.session_events import (
    AssistantMessageData,
    AssistantMessageDeltaData,
    AssistantReasoningDeltaData,
    SessionErrorData,
    SessionEvent,
)

from src.AIModels.openai import AIMessageInput, AIStreamChunk
from src.core.errors import AppError

logger = logging.getLogger(__name__)
PROBE_PROMPT = "Reply with exactly COPILOT_OK. Do not use tools."
EXPECTED_ANSWER = "COPILOT_OK"
DATA_DIRECTORY = Path.home() / ".cache" / "enterprise-api" / "copilot"


class CopilotProbeError(Exception):
    """The SDK could not verify an authenticated model response."""


class CopilotError(Exception):
    def __init__(self, message: str, *, code: str = "COPILOT_STREAM_FAILED") -> None:
        super().__init__(message)
        self.code = code


class CopilotService:
    """Own a local runtime and a cancellable, non-blocking startup login task."""

    def __init__(
        self, *, cli_path: str = "", runtime_path: str = "",
        model: str = "auto", auto_login: bool = True,
    ) -> None:
        self.cli_path = cli_path
        self.runtime_path = runtime_path
        self.model = model
        self.auto_login = auto_login
        self.status: Literal[
            "starting", "authenticating", "ready", "login_required", "failed",
        ] = "starting"
        self.error_code = ""
        self._client: CopilotClient | None = None
        self._task: asyncio.Task[None] | None = None
        self._login: asyncio.subprocess.Process | None = None
        self._directory: TemporaryDirectory[str] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._initialize(), name="copilot-startup")

    async def _initialize(self) -> None:
        try:
            cli = shutil.which(self.cli_path or "copilot")
            runtime = self.runtime_path or cli
            if not runtime:
                self.status = "failed"
                self.error_code = "COPILOT_CLI_NOT_FOUND"
                logger.error(
                    "Copilot CLI not found. Install the official CLI, then restart "
                    "the application. On macOS: brew install --cask copilot-cli"
                )
                return
            self._directory = TemporaryDirectory(prefix="enterprise-api-chat-")
            DATA_DIRECTORY.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._client = CopilotClient(
                connection=RuntimeConnection.for_stdio(path=runtime),
                working_directory=self._directory.name,
                base_directory=str(DATA_DIRECTORY),
                mode="copilot-cli",
            )
            async with asyncio.timeout(30):
                await self._client.start()
                authenticated = (await self._client.get_auth_status()).isAuthenticated
            if not authenticated:
                self.status = "login_required"
                self.error_code = "COPILOT_LOGIN_REQUIRED"
                if not self.auto_login:
                    logger.warning("Copilot needs login; automatic local login is disabled.")
                    return
                if cli is None:
                    self.error_code = "COPILOT_CLI_NOT_FOUND"
                    logger.error("Official Copilot CLI is required for automatic browser login.")
                    return
                await self._authenticate(cli)
            else:
                self.status = "ready"
                logger.info("Copilot is authenticated and ready.")
        except (OSError, RuntimeError, ValueError, TimeoutError, JsonRpcError, ProcessExitedError):
            self.status = "failed"
            self.error_code = "COPILOT_STARTUP_FAILED"
            logger.exception("Copilot startup or login failed; other API routes remain available.")

    async def _authenticate(self, cli: str) -> None:
        # A per-user advisory lock prevents concurrent local workers opening login flows.
        import fcntl

        with (DATA_DIRECTORY / "login.lock").open("a") as lock:
            async with asyncio.timeout(300):
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        await asyncio.sleep(1)
                try:
                    assert self._client is not None
                    await self._client.stop()
                    await self._client.start()
                    if not (await self._client.get_auth_status()).isAuthenticated:
                        self.status = "authenticating"
                        logger.info(
                            "Starting official Copilot login. Complete enterprise "
                            "authorization in the browser; follow CLI output below."
                        )
                        self._login = await asyncio.create_subprocess_exec(
                            cli, "login",
                            cwd=self._directory.name if self._directory else None,
                            env={**os.environ, "COPILOT_HOME": str(DATA_DIRECTORY)},
                            stdin=asyncio.subprocess.DEVNULL,
                        )
                        try:
                            return_code = await self._login.wait()
                        finally:
                            await self._stop_login()
                        if return_code != 0:
                            raise RuntimeError(f"Copilot login exited with code {return_code}")
                        await self._client.stop()
                        await self._client.start()
                    if not (await self._client.get_auth_status()).isAuthenticated:
                        raise RuntimeError("Copilot CLI completed without usable SDK authentication")
                    self.status = "ready"
                    self.error_code = ""
                    logger.info("Copilot enterprise authorization completed.")
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def ensure_ready(self) -> None:
        if self.status != "ready":
            raise AppError(
                code=self.error_code or "COPILOT_STARTING",
                message=f"Copilot is {self.status}; check server logs and finish local login.",
                status_code=503,
            )

    async def _stop_login(self) -> None:
        process = self._login
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()
        self._login = None

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        await self._stop_login()
        try:
            if self._client is not None:
                await self._client.stop()
        finally:
            if self._directory is not None:
                self._directory.cleanup()

    async def stream_chat(
        self, messages: list[AIMessageInput],
    ) -> AsyncIterator[AIStreamChunk]:
        self.ensure_ready()
        assert self._client is not None
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        # Each HTTP turn has its own SDK session; history is structured input, not instructions.
        prompt = json.dumps(
            [m for m in messages if m["role"] != "system"], ensure_ascii=False,
        )
        try:
            async with await create_chat_session(
                self._client,
                model=self.model,
                working_directory=self._directory.name if self._directory else None,
                system=system + "\nThe prompt is a JSON conversation history. "
                "Respond to its last user message. Do not use tools.",
            ) as session:
                queue: asyncio.Queue[AIStreamChunk | CopilotError | None] = asyncio.Queue()
                content_received = False

                def on_event(event: SessionEvent) -> None:
                    nonlocal content_received
                    if event.agent_id:
                        return
                    if isinstance(event.data, AssistantMessageDeltaData):
                        content_received = True
                        queue.put_nowait(AIStreamChunk("content", event.data.delta_content))
                    elif isinstance(event.data, AssistantReasoningDeltaData):
                        queue.put_nowait(AIStreamChunk("reasoning", event.data.delta_content))
                    elif isinstance(event.data, SessionErrorData):
                        logger.error("Copilot session failed: %s", event.data.error_type)
                        queue.put_nowait(CopilotError("Copilot session failed"))

                async def send() -> None:
                    try:
                        response = await session.send_and_wait(prompt, timeout=300)
                        if (
                            response is None
                            or not isinstance(response.data, AssistantMessageData)
                            or not response.data.content.strip()
                            or response.data.tool_requests
                        ):
                            queue.put_nowait(CopilotError("Copilot returned no final answer"))
                        elif not content_received:
                            queue.put_nowait(AIStreamChunk("content", response.data.content))
                    except (
                        OSError, RuntimeError, ValueError, TimeoutError,
                        JsonRpcError, ProcessExitedError,
                    ):
                        logger.exception("Copilot model request failed.")
                        queue.put_nowait(CopilotError("Copilot model request failed"))
                    finally:
                        queue.put_nowait(None)

                unsubscribe = session.on(on_event)
                sender = asyncio.create_task(send())
                completed = False
                try:
                    while (chunk := await queue.get()) is not None:
                        if isinstance(chunk, CopilotError):
                            raise chunk
                        yield chunk
                    completed = True
                finally:
                    sender.cancel()
                    try:
                        with suppress(asyncio.CancelledError):
                            await sender
                    finally:
                        unsubscribe()
                        if not completed:
                            await session.abort()
        except (
            OSError, RuntimeError, ValueError, TimeoutError,
            JsonRpcError, ProcessExitedError,
        ) as exc:
            logger.exception("Copilot stream failed.")
            raise CopilotError("Copilot stream failed") from exc


def deny_permission(
    _request: PermissionRequest, _invocation: PermissionInvocation,
) -> PermissionDecisionReject:
    return PermissionDecisionReject(feedback="This chat service does not permit tool access.")


async def create_chat_session(
    client: CopilotClient, *, model: str, working_directory: str | None, system: str,
) -> CopilotSession:
    return await client.create_session(
        model=model,
        on_permission_request=deny_permission,
        available_tools=[],
        excluded_tools=ToolSet().add_builtin("*").add_mcp("*").add_custom("*"),
        working_directory=working_directory,
        enable_config_discovery=False,
        enable_file_hooks=False,
        enable_skills=False,
        enable_host_git_operations=False,
        enable_session_store=False,
        enable_session_telemetry=False,
        skip_embedding_retrieval=True,
        enable_on_demand_instruction_discovery=False,
        custom_agents_local_only=True,
        coauthor_enabled=False,
        manage_schedule_enabled=False,
        included_builtin_skills=[],
        plugin_directories=[],
        agent_directories=[],
        instruction_directories=[],
        skip_custom_instructions=True,
        mcp_servers={},
        streaming=True,
        system_message={"mode": "replace", "content": system},
    )


async def probe_copilot(
    *, model: str = "auto", runtime_path: str | None = None,
) -> str:
    """Send only a fixed test prompt, without repository or database access."""
    with TemporaryDirectory(prefix="enterprise-api-copilot-") as directory:
        async with CopilotClient(
            connection=RuntimeConnection.for_stdio(path=runtime_path),
            working_directory=directory,
            base_directory=str(DATA_DIRECTORY),
            mode="copilot-cli",
        ) as client:
            status = await client.get_auth_status()
            if not status.isAuthenticated:
                raise CopilotProbeError(
                    "COPILOT_NOT_AUTHENTICATED: run `copilot login` with the account "
                    "that has your enterprise Copilot seat, then retry. "
                    "The current VS Code chat login is not inherited."
                )

            async with await create_chat_session(
                client,
                model=model,
                working_directory=directory,
                system="Answer the test prompt literally. Do not use tools.",
            ) as session:
                response = await session.send_and_wait(PROBE_PROMPT, timeout=60)
                if (
                    response is None
                    or not isinstance(response.data, AssistantMessageData)
                    or response.data.content.strip() != EXPECTED_ANSWER
                    or response.data.tool_requests
                ):
                    raise CopilotProbeError(
                        "COPILOT_PROBE_FAILED: no exact COPILOT_OK model response."
                    )
                return response.data.content.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="auto")
    parser.add_argument(
        "--runtime-path",
        help="Optional official runtime executable; otherwise use SDK resolution.",
    )
    args = parser.parse_args()
    try:
        answer = asyncio.run(
            probe_copilot(model=args.model, runtime_path=args.runtime_path)
        )
    except CopilotProbeError as exc:
        logger.error("%s", exc)
        return 1
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
