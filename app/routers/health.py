from fastapi import APIRouter
from app.models import RootStatusResponse, HealthResponse

router = APIRouter(tags=["Health & Status"])


@router.get(
    "/",
    response_model=RootStatusResponse,
    summary="API Root Information",
    description="Returns basic application status information."
)
async def get_root():
    return RootStatusResponse()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Unprotected health check endpoint for container probes and status monitoring."
)
async def get_health():
    return HealthResponse()
