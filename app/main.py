import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi

from app.config import settings
from app.auth import AuthException
from app.scraper import close_browser
from app.routers import health, stories

# Configure application logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("tiktok_story_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for graceful Playwright browser shutdown."""
    logger.info("Starting TikTok Story API service...")
    yield
    logger.info("Shutting down TikTok Story API service...")
    await close_browser()

app = FastAPI(
    title="TikTok Story API",
    description="Self-hosted API for extracting TikTok stories and serving proxy media for n8n automations.",
    version="1.0.0",
    lifespan=lifespan
)

# Exception handlers for uniform JSON error responses
@app.exception_handler(AuthException)
async def auth_exception_handler(request: Request, exc: AuthException):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"success": False, "error": "Internal server error"}
    )

# Include API Routers
app.include_router(health.router)
app.include_router(stories.router)


# OpenAPI security customization for Swagger UI
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="TikTok Story API",
        version="1.0.0",
        description="Self-hosted FastAPI for extracting TikTok active stories and proxying media downloads for n8n automations.",
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "Supply your secret key configured in API_KEYS environment variable."
        },
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "description": "Bearer token authentication format."
        }
    }

    # Add security requirement to protected endpoints
    protected_paths = ["/stories", "/stories/latest", "/download/{story_id}"]
    for path, path_item in openapi_schema.get("paths", {}).items():
        if path in protected_paths:
            for method in path_item:
                path_item[method]["security"] = [
                    {"ApiKeyAuth": []},
                    {"BearerAuth": []}
                ]

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
