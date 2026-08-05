# SQLAlchemy 定义整数字段、外键和文本字段。
from sqlalchemy import ForeignKey, Integer, Text

# SQLAlchemy ORM 提供模型字段声明。
from sqlalchemy.orm import Mapped, mapped_column

# 数据库基类将 Message 注册为 SQLAlchemy 可管理的数据表。
from src.db.base import Base


# message API 写入的消息表；id 是数据库自增主键，user_id 对应接口里的 user_id。
class Message(Base):
    __tablename__ = "message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("profile.user_id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)