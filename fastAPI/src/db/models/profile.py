# SQLAlchemy 定义整数字段、字符串字段和 ORM 字段声明工具。
from sqlalchemy import Integer, String

# SQLAlchemy ORM 提供模型字段声明。
from sqlalchemy.orm import Mapped, mapped_column

# 数据库基类将 Profile 注册为 SQLAlchemy 可管理的数据表。
from src.db.base import Base


# profile 表；id 是数据库自增主键，user_id 对应接口里的 user_id。
class Profile(Base):
    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)