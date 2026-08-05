# 基类模块提供所有 ORM 表共享的元数据注册入口。
from src.db.base import Base

# 对话模型模块在导入时将会话表和消息表注册到 Base 元数据。
from src.db.models.chat import ChatConversation, ChatMessage

# message 模型模块在导入时将 message 表注册到 Base 元数据。
from src.db.models.message import Message

# profile 模型模块在导入时将 profile 表注册到 Base 元数据。
from src.db.models.profile import Profile

# 集中导入模型，使 Alembic 加载 Base 时能够发现全部数据表。
__all__ = ["Base", "ChatConversation", "ChatMessage", "Message", "Profile"]