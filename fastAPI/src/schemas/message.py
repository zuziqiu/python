from pydantic import BaseModel, Field


class MessageRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=10_000)


class MessageResponse(BaseModel):
    user_id: str
    text: str