import asyncio

# logging.config 根据 alembic.ini 的日志配置初始化迁移命令日志。
from logging.config import fileConfig

# Alembic 负责读取并执行数据库结构迁移。
from alembic import context

# SQLAlchemy 异步引擎用于通过 asyncpg 连接 PostgreSQL 执行迁移。
from sqlalchemy.ext.asyncio import create_async_engine

# 应用配置模块提供与服务一致的数据库连接串。
from src.core.config import get_settings

# 模型模块导出已注册的表元数据，供 Alembic 比对和运行迁移。
from src.db.models import Base

# Alembic 运行时配置对象；连接串与应用使用同一份环境配置。
config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 用 ORM 模型元数据生成或校验迁移需要的表结构。
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """不连接数据库，仅生成可执行 SQL。"""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: object) -> None:
    """在已建立的连接中执行一个迁移事务。"""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """使用 asyncpg 建立异步连接并运行在线迁移。"""
    connectable = create_async_engine(config.get_main_option("sqlalchemy.url"))

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """作为 Alembic 在线入口运行异步迁移协程。"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()