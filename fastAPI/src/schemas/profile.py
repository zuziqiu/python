# Pydantic 提供接口请求和响应的数据校验模型。
from pydantic import BaseModel, Field


class ProfileUpdateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)


class ProfileResponse(BaseModel):
    user_id: str
    name: str