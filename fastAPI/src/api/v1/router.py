from fastapi import APIRouter

from src.api.v1.text import router as text_router

router = APIRouter()
router.include_router(text_router)