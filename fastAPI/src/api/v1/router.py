from fastapi import APIRouter

from src.api.v1.message import router as message_router
from src.api.v1.profile import router as profile_router

router = APIRouter()
router.include_router(message_router)
router.include_router(profile_router)