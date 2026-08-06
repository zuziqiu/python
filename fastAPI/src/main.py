# collections.abc 的 AsyncIterator 标注生命周期异步生成器返回的值类型。
from collections.abc import AsyncIterator

# contextlib 把异步生成器包装为 FastAPI 可执行的生命周期上下文。
from contextlib import asynccontextmanager

# FastAPI 提供应用生命周期和 HTTP 异常响应类型。
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# v1 路由聚合器导出所有当前版本的 HTTP 接口。
from src.api.v1.router import router as api_v1_router

# 配置模块读取应用名称、日志级别和 API 前缀等环境配置。
from src.core.config import get_settings

# 业务异常模块定义统一错误类型，供异常处理器转换为 HTTP 响应。
from src.core.errors import AppError

# 日志模块在应用启动时配置结构化日志输出。
from src.core.logging import configure_logging

# 数据库模块在启动时校验 PostgreSQL 连接，并在停止时释放连接池。
from src.db.session import close_database, connect_database

# HTTP 中间件为每个请求添加请求 ID、耗时记录和访问日志。
from src.middleware import request_context_middleware

# 响应模型模块定义统一的错误 JSON 结构。
from src.schemas.common import ErrorDetail, ErrorResponse


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    # 服务开始接收请求前执行 SELECT 1；连接串、账号或 PostgreSQL 不可用时启动失败。
    await connect_database()
    # 正常或者异常关闭服务都能最终进入 close_database
    try:
        yield
    finally:
        # 服务停止时释放数据库连接池，避免连接长期占用。
        await close_database()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.middleware("http")(request_context_middleware)
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        response = ErrorResponse(
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
                request_id=getattr(request.state, "request_id", None),
            )
        )
        return JSONResponse(status_code=exc.status_code, content=response.model_dump())

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        details = [
            {
                key: value
                for key, value in error.items()
                if key not in {"ctx", "input"}
            }
            for error in exc.errors()
        ]
        response = ErrorResponse(
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message="Request validation failed",
                request_id=getattr(request.state, "request_id", None),
                details=details,
            )
        )
        return JSONResponse(status_code=422, content=jsonable_encoder(response))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, _: Exception) -> JSONResponse:
        response = ErrorResponse(
            error=ErrorDetail(
                code="INTERNAL_SERVER_ERROR",
                message="Internal server error",
                request_id=getattr(request.state, "request_id", None),
            )
        )
        return JSONResponse(status_code=500, content=response.model_dump())

    return app


app = create_app()