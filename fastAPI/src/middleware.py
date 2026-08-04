import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response

logger = logging.getLogger("app.access")

# 包裹每一次 HTTP 请求，补充请求上下文、响应头和访问日志。
# 执行流程：先读取或生成请求 ID，保存到 request.state 供后续路由和异常处理器使用；
# 再通过 call_next 把请求交给后续处理链；响应生成后，
# 写回 X-Request-ID 响应头，并记录方法、路径、状态码和耗时。
async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    request.state.request_id = request_id
    started_at = time.perf_counter()

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id

    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
        },
    )
    return response