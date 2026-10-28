import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from copilot import GetAuthStatusResponse
from copilot.session_events import (
    AssistantMessageData,
    AssistantMessageDeltaData,
    SessionEvent,
    SessionEventType,
)

from src.AIModels import copilot
from src.core.config import Settings
from src.core.errors import AppError


@pytest.fixture
def sdk(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, AsyncMock, AsyncMock]:
    constructor = MagicMock()
    client = AsyncMock()
    session = AsyncMock()
    constructor.return_value.__aenter__.return_value = client
    client.get_auth_status.return_value = GetAuthStatusResponse(isAuthenticated=True)
    client.create_session.return_value.__aenter__.return_value = session
    session.send_and_wait.return_value = SessionEvent(
        data=AssistantMessageData(content="COPILOT_OK", message_id="probe"),
        id=uuid4(),
        timestamp=datetime.now(UTC),
        type=SessionEventType.ASSISTANT_MESSAGE,
    )
    monkeypatch.setattr(copilot, "CopilotClient", constructor)
    return constructor, client, session


def test_probe_verifies_real_response_contract_and_disables_tools(
    sdk: tuple[MagicMock, AsyncMock, AsyncMock],
) -> None:
    constructor, client, session = sdk

    assert asyncio.run(copilot.probe_copilot()) == "COPILOT_OK"
    assert constructor.call_args.kwargs["mode"] == "copilot-cli"
    assert constructor.call_args.kwargs["base_directory"] == str(copilot.DATA_DIRECTORY)
    assert constructor.call_args.kwargs["base_directory"] != (
        constructor.call_args.kwargs["working_directory"]
    )
    options = client.create_session.call_args.kwargs
    assert options["excluded_tools"].to_list() == [
        "builtin:*", "mcp:*", "custom:*",
    ]
    assert options["available_tools"] == []
    assert options["enable_config_discovery"] is False
    assert options["enable_file_hooks"] is False
    assert options["enable_skills"] is False
    assert options["enable_host_git_operations"] is False
    assert options["enable_session_store"] is False
    assert options["skip_custom_instructions"] is True
    assert options["mcp_servers"] == {}
    assert options["enable_session_telemetry"] is False
    assert options["skip_embedding_retrieval"] is True
    assert options["included_builtin_skills"] == []
    session.send_and_wait.assert_awaited_once_with(copilot.PROBE_PROMPT, timeout=60)
    client.create_session.return_value.__aexit__.assert_awaited_once()
    constructor.return_value.__aexit__.assert_awaited_once()


def test_probe_rejects_missing_auth_before_sending_prompt(
    sdk: tuple[MagicMock, AsyncMock, AsyncMock],
) -> None:
    _, client, session = sdk
    client.get_auth_status.return_value = GetAuthStatusResponse(isAuthenticated=False)

    with pytest.raises(copilot.CopilotProbeError, match="COPILOT_NOT_AUTHENTICATED"):
        asyncio.run(copilot.probe_copilot())

    client.create_session.assert_not_awaited()
    session.send_and_wait.assert_not_awaited()


@pytest.mark.parametrize("answer", [None, "", "Some other answer"])
def test_probe_never_reports_unexpected_answers_as_success(
    sdk: tuple[MagicMock, AsyncMock, AsyncMock], answer: str | None,
) -> None:
    _, _, session = sdk
    if answer is None:
        session.send_and_wait.return_value = None
    else:
        session.send_and_wait.return_value.data.content = answer

    with pytest.raises(copilot.CopilotProbeError, match="COPILOT_PROBE_FAILED"):
        asyncio.run(copilot.probe_copilot())


def test_probe_surfaces_upstream_errors_and_closes_session(
    sdk: tuple[MagicMock, AsyncMock, AsyncMock],
) -> None:
    constructor, client, session = sdk
    session.send_and_wait.side_effect = RuntimeError("model unavailable")

    with pytest.raises(RuntimeError, match="model unavailable"):
        asyncio.run(copilot.probe_copilot())

    client.create_session.return_value.__aexit__.assert_awaited_once()
    constructor.return_value.__aexit__.assert_awaited_once()


@pytest.fixture
def service_sdk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> tuple[AsyncMock, AsyncMock]:
    client = AsyncMock()
    session = AsyncMock()
    session.on = MagicMock(return_value=MagicMock())
    client.create_session.return_value.__aenter__.return_value = session
    client.get_auth_status.return_value = GetAuthStatusResponse(isAuthenticated=True)
    monkeypatch.setattr(copilot, "CopilotClient", MagicMock(return_value=client))
    monkeypatch.setattr(copilot.shutil, "which", lambda _: "/official/copilot")
    monkeypatch.setattr(copilot, "DATA_DIRECTORY", tmp_path / "copilot")
    return client, session


def test_service_reuses_login_without_spawning_browser(
    service_sdk: tuple[AsyncMock, AsyncMock], monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = service_sdk
    spawn = AsyncMock()
    monkeypatch.setattr(copilot.asyncio, "create_subprocess_exec", spawn)

    async def run() -> None:
        service = copilot.CopilotService()
        service.start()
        assert service._task is not None
        await service._task
        service.ensure_ready()
        assert service.status == "ready"
        await service.close()

    asyncio.run(run())
    spawn.assert_not_awaited()
    client.stop.assert_awaited_once()


def test_startup_logs_in_and_rechecks_sdk_authentication(
    service_sdk: tuple[AsyncMock, AsyncMock], monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = service_sdk
    client.get_auth_status.side_effect = [
        GetAuthStatusResponse(isAuthenticated=value) for value in (False, False, True)
    ]
    process = MagicMock(returncode=0)
    process.wait = AsyncMock(return_value=0)
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(copilot.asyncio, "create_subprocess_exec", spawn)

    async def run() -> None:
        service = copilot.CopilotService()
        service.start()
        assert service._task is not None
        await service._task
        assert service.status == "ready"
        assert service.error_code == ""
        await service.close()

    asyncio.run(run())
    assert spawn.call_args.args == ("/official/copilot", "login")
    assert spawn.call_args.kwargs["env"]["COPILOT_HOME"] == str(copilot.DATA_DIRECTORY)
    assert client.start.await_count == 3
    assert client.get_auth_status.await_count == 3


def test_disabled_auto_login_returns_503_without_opening_browser(
    service_sdk: tuple[AsyncMock, AsyncMock], monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = service_sdk
    client.get_auth_status.return_value = GetAuthStatusResponse(isAuthenticated=False)
    spawn = AsyncMock()
    monkeypatch.setattr(copilot.asyncio, "create_subprocess_exec", spawn)

    async def run() -> None:
        service = copilot.CopilotService(auto_login=False)
        service.start()
        assert service._task is not None
        await service._task
        with pytest.raises(AppError) as error:
            service.ensure_ready()
        assert error.value.status_code == 503
        assert error.value.code == "COPILOT_LOGIN_REQUIRED"
        await service.close()

    asyncio.run(run())
    spawn.assert_not_awaited()


def test_missing_cli_keeps_service_explicitly_unavailable(
    service_sdk: tuple[AsyncMock, AsyncMock], monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = service_sdk
    monkeypatch.setattr(copilot.shutil, "which", lambda _: None)

    async def run() -> None:
        service = copilot.CopilotService()
        service.start()
        assert service._task is not None
        await service._task
        assert service.status == "failed"
        assert service.error_code == "COPILOT_CLI_NOT_FOUND"
        await service.close()

    asyncio.run(run())
    client.start.assert_not_awaited()


def test_failed_login_is_not_reported_as_ready(
    service_sdk: tuple[AsyncMock, AsyncMock], monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = service_sdk
    client.get_auth_status.return_value = GetAuthStatusResponse(isAuthenticated=False)
    process = MagicMock(returncode=1)
    process.wait = AsyncMock(return_value=1)
    monkeypatch.setattr(
        copilot.asyncio, "create_subprocess_exec", AsyncMock(return_value=process),
    )

    async def run() -> None:
        service = copilot.CopilotService()
        service.start()
        assert service._task is not None
        await service._task
        assert service.status == "failed"
        assert service.error_code == "COPILOT_STARTUP_FAILED"
        await service.close()

    asyncio.run(run())


def test_shutdown_terminates_pending_login_and_runtime(
    service_sdk: tuple[AsyncMock, AsyncMock], monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = service_sdk
    client.get_auth_status.return_value = GetAuthStatusResponse(isAuthenticated=False)

    async def run() -> None:
        entered = asyncio.Event()
        process = MagicMock(returncode=None)

        async def wait() -> int:
            if entered.is_set():
                return 0
            entered.set()
            await asyncio.Event().wait()
            return 0

        process.wait = AsyncMock(side_effect=wait)
        monkeypatch.setattr(
            copilot.asyncio, "create_subprocess_exec", AsyncMock(return_value=process),
        )
        service = copilot.CopilotService()
        service.start()
        await asyncio.wait_for(entered.wait(), timeout=1)
        await service.close()
        process.terminate.assert_called_once()
        assert client.stop.await_count >= 2

    asyncio.run(run())


def test_stream_preserves_deltas_and_closes_isolated_session(
    service_sdk: tuple[AsyncMock, AsyncMock],
) -> None:
    client, session = service_sdk

    async def send(prompt: str, *, timeout: float) -> SessionEvent:
        assert json.loads(prompt) == [{"role": "user", "content": "Hello"}]
        assert timeout == 300
        handler = session.on.call_args.args[0]
        handler(SessionEvent(
            data=AssistantMessageDeltaData(delta_content="Answer", message_id="turn"),
            id=uuid4(), timestamp=datetime.now(UTC),
            type=SessionEventType.ASSISTANT_MESSAGE_DELTA,
        ))
        return SessionEvent(
            data=AssistantMessageData(content="Answer", message_id="turn"),
            id=uuid4(), timestamp=datetime.now(UTC),
            type=SessionEventType.ASSISTANT_MESSAGE,
        )

    session.send_and_wait.side_effect = send

    async def run() -> None:
        service = copilot.CopilotService()
        service.start()
        assert service._task is not None
        await service._task
        chunks = [chunk async for chunk in service.stream_chat([
            {"role": "system", "content": "Server rules"},
            {"role": "user", "content": "Hello"},
        ])]
        assert chunks == [copilot.AIStreamChunk("content", "Answer")]
        assert client.create_session.call_args.kwargs["available_tools"] == []
        assert client.create_session.call_args.kwargs["streaming"] is True
        session.on.return_value.assert_called_once()
        session.abort.assert_not_awaited()
        client.create_session.return_value.__aexit__.assert_awaited_once()
        await service.close()

    asyncio.run(run())


@pytest.mark.parametrize("failure", [TimeoutError, copilot.JsonRpcError])
def test_stream_surfaces_upstream_failure_and_aborts(
    service_sdk: tuple[AsyncMock, AsyncMock], failure: type[Exception],
) -> None:
    _, session = service_sdk
    session.send_and_wait.side_effect = (
        copilot.JsonRpcError(-1, "denied") if failure is copilot.JsonRpcError else failure()
    )

    async def run() -> None:
        service = copilot.CopilotService()
        service.start()
        assert service._task is not None
        await service._task
        with pytest.raises(copilot.CopilotError):
            _ = [chunk async for chunk in service.stream_chat([
                {"role": "user", "content": "Hello"},
            ])]
        session.abort.assert_awaited_once()
        await service.close()

    asyncio.run(run())


def test_client_disconnect_aborts_running_session(
    service_sdk: tuple[AsyncMock, AsyncMock],
) -> None:
    _, session = service_sdk

    async def send(prompt: str, *, timeout: float) -> None:
        handler = session.on.call_args.args[0]
        handler(SessionEvent(
            data=AssistantMessageDeltaData(delta_content="Partial", message_id="turn"),
            id=uuid4(), timestamp=datetime.now(UTC),
            type=SessionEventType.ASSISTANT_MESSAGE_DELTA,
        ))
        await asyncio.Event().wait()

    session.send_and_wait.side_effect = send

    async def run() -> None:
        service = copilot.CopilotService()
        service.start()
        assert service._task is not None
        await service._task
        stream = service.stream_chat([{"role": "user", "content": "Hello"}])
        assert (await anext(stream)).delta == "Partial"
        await stream.aclose()
        session.abort.assert_awaited_once()
        session.on.return_value.assert_called_once()
        await service.close()

    asyncio.run(run())


def test_concurrent_local_workers_only_launch_one_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    authenticated = False
    clients = [AsyncMock(), AsyncMock()]
    monkeypatch.setattr(copilot, "CopilotClient", MagicMock(side_effect=clients))
    monkeypatch.setattr(copilot.shutil, "which", lambda _: "/official/copilot")
    monkeypatch.setattr(copilot, "DATA_DIRECTORY", tmp_path / "copilot")

    async def auth_status() -> GetAuthStatusResponse:
        return GetAuthStatusResponse(isAuthenticated=authenticated)

    for client in clients:
        client.get_auth_status.side_effect = auth_status

    async def run() -> None:
        started = asyncio.Event()
        finish = asyncio.Event()
        process = MagicMock(returncode=0)

        async def wait() -> int:
            nonlocal authenticated
            started.set()
            await finish.wait()
            authenticated = True
            return 0

        process.wait = AsyncMock(side_effect=wait)
        spawn = AsyncMock(return_value=process)
        monkeypatch.setattr(copilot.asyncio, "create_subprocess_exec", spawn)
        first = copilot.CopilotService()
        second = copilot.CopilotService()
        first.start()
        await asyncio.wait_for(started.wait(), timeout=1)
        second.start()
        # Let the second worker reach the advisory lock while login is pending.
        await asyncio.sleep(0)
        finish.set()
        assert first._task is not None and second._task is not None
        await asyncio.wait_for(asyncio.gather(first._task, second._task), timeout=3)
        assert first.status == second.status == "ready"
        spawn.assert_awaited_once()
        await first.close()
        await second.close()

    asyncio.run(run())


@pytest.mark.parametrize("provider", ["copilot", "openai"])
def test_application_lifespan_starts_selected_provider_without_waiting_for_login(
    monkeypatch: pytest.MonkeyPatch, provider: str,
) -> None:
    from fastapi import FastAPI

    import src.main as application

    settings = Settings(_env_file=None, ai_provider=provider)
    monkeypatch.setattr(application, "get_settings", lambda: settings)
    monkeypatch.setattr(application, "configure_logging", MagicMock())
    connect = AsyncMock()
    disconnect = AsyncMock()
    monkeypatch.setattr(application, "connect_database", connect)
    monkeypatch.setattr(application, "close_database", disconnect)
    service = MagicMock()
    service.close = AsyncMock()
    monkeypatch.setattr(application, "CopilotService", MagicMock(return_value=service))
    openai_client = MagicMock()
    openai_client.close = AsyncMock()
    create_openai = MagicMock(return_value=openai_client)
    monkeypatch.setattr(application, "create_openai_client", create_openai)

    async def run() -> None:
        app = FastAPI()
        async with application.lifespan(app):
            connect.assert_awaited_once()
            if provider == "copilot":
                assert app.state.copilot_service is service
                service.start.assert_called_once()
                create_openai.assert_not_called()
            else:
                assert app.state.openai_client is openai_client
                service.start.assert_not_called()
        disconnect.assert_awaited_once()
        if provider == "copilot":
            service.close.assert_awaited_once()
        else:
            openai_client.close.assert_awaited_once()

    asyncio.run(run())
