# collections.abc 的 AsyncIterator 标注数据库会话依赖按异步生成器产出会话。
from collections.abc import AsyncIterator

# SQLAlchemy text 用于执行不依赖 ORM 模型的数据库连通性查询。
from sqlalchemy import text

# SQLAlchemy 异步模块负责创建 PostgreSQL 连接池、会话和事务。
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 配置模块提供 PostgreSQL 连接串和连接池参数。
from src.core.config import get_settings

# 使用项目配置创建唯一的异步连接池，并在应用关闭时统一释放。
settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout_seconds,
)
# 每次业务操作从连接池取得独立会话，避免请求之间共享事务状态。
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def connect_database() -> None:
    """启动时执行轻量查询，确认 PostgreSQL 连接可用。"""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """提供一次数据库事务；正常结束提交，异常时回滚。"""
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_database() -> None:
    """在应用停止时关闭连接池并释放数据库连接。"""
    await engine.dispose()