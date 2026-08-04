from fastapi import APIRouter

from src.schemas.text import TextRequest, TextResponse

router = APIRouter(tags=["text"])


@router.post("/text", response_model=TextResponse)
def receive_text(payload: TextRequest) -> TextResponse:
    return TextResponse(text=payload.text)