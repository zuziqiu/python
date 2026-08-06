from fastapi import APIRouter

from src.api.v1.conversation import router as conversation_router
from src.api.v1.profile import router as profile_router

router = APIRouter()
router.include_router(conversation_router)
router.include_router(profile_router)