# Pydantic 提供接口请求和响应的数据校验模型。
from pydantic import BaseModel, Field


class ProfileUpdateRequest(BaseModel):
    # 要更新的用户标识，用于定位对应的 profile。
    user_id: str = Field(min_length=1, max_length=64)
    # 用户的新名称；不能为空，且最多 255 个字符。
    name: str = Field(min_length=1, max_length=255)


class ProfileResponse(BaseModel):
    # 返回的 profile 所属用户标识。
    user_id: str
    # 返回的用户名称。
    name: str