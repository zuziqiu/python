from fastapi import APIRouter, Request

from src.AIModels.copilot import CopilotService
from src.api.v1.conversation import router as conversation_router
from src.api.v1.profile import router as profile_router

router = APIRouter()
router.include_router(conversation_router)
router.include_router(profile_router)


@router.get("/copilot/status", tags=["copilot"])
async def copilot_status(request: Request) -> dict[str, str]:
    service: CopilotService | None = getattr(request.app.state, "copilot_service", None)
    if service is None:
        return {"status": "disabled", "error_code": ""}
    return {"status": service.status, "error_code": service.error_code}