from pydantic import BaseModel, Field


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)


class TextResponse(BaseModel):
    text: str