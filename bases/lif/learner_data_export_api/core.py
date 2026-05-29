from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from lif.learner_data_export_api import learner_data_export_endpoints
from lif.logging import get_logger
from lif.mdr_auth.core import AuthMiddleware
from lif.mdr_utils.config import get_settings

logger = get_logger(__name__)
settings = get_settings()
app = FastAPI(title="LIF Learner Data Export API", description="API for the LIF Learner Data Export", version="1.0.0")

app.add_middleware(AuthMiddleware)
# Configure CORS middleware
cors_origins = [origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()]
cors_methods = [method.strip() for method in settings.cors_allow_methods.split(",") if method.strip()]
cors_headers = (
    [header.strip() for header in settings.cors_allow_headers.split(",") if header.strip()]
    if settings.cors_allow_headers != "*"
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=cors_methods,
    allow_headers=cors_headers,
)


# --- API Endpoints ---


@app.get("/health")
async def health_check():
    """
    Health check endpoint to verify the API is running
    """
    return {"status": "ok"}


app.include_router(learner_data_export_endpoints.router, prefix="")
