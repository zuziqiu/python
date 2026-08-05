# SQLAlchemy ORM 用这个基类把 Python 模型映射为数据库表。
from sqlalchemy.orm import DeclarativeBase


# 所有 ORM 模型共用的基类，Alembic 通过它收集表结构。
class Base(DeclarativeBase):
    pass