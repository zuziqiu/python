# functools 的 lru_cache 缓存配置实例，避免每次读取环境变量都重新创建对象。
from functools import lru_cache

# pydantic-settings 用于从 .env 和环境变量读取、校验数据库配置。
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Enterprise API"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    # PostgreSQL 异步连接串；生产环境通过 APP_DATABASE_URL 覆盖默认本地值。
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/enterprise_api"
    # 连接池容量与等待时间，避免每个请求都新建数据库连接。
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout_seconds: int = 30
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "deepseek-ai/DeepSeek-R1"
    siliconflow_temperature: float = 0.7
    siliconflow_max_tokens: int = 4096

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()