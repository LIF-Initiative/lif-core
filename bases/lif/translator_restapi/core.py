from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from uuid import uuid4
from lif.exceptions.core import LIFException, ResourceNotFoundException
from lif.translator.core import TranslatorConfig, Translator
from lif.logging.core import get_logger

logger = get_logger(__name__)
app = FastAPI()


@app.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}


@app.post("/translate/source/{source_schema_id}/target/{target_schema_id}")
async def translate(request: Request, source_schema_id: str, target_schema_id: str, input_data: dict) -> dict:
    translator_config = TranslatorConfig(source_schema_id=source_schema_id, target_schema_id=target_schema_id)
    translator = Translator(translator_config)
    tenant_schema = request.headers.get("X-API-Tenant-Schema")
    result = await translator.run(input_data, tenant_schema=tenant_schema)
    return result


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Extract and format the error details
    error_details = []
    for error in exc.errors():
        loc = ".".join(map(str, error["loc"]))
        msg = error["msg"]
        ctx = error.get("ctx", {})
        error_details.append(f"Location: {loc}, Message: {msg}, Context: {ctx}")

    # Log the details
    logger.error(f"Pydantic Validation Error (422) for request to {request.url.path}: {'; '.join(error_details)}")

    # Return a custom JSON response to the client (optional, but good practice)
    return JSONResponse(
        status_code=422,
        content={
            "status_code": "422",
            "path": request.url.path,
            "message": "Validation error.",
            "detail": exc.errors(),
        },
    )


@app.exception_handler(ValueError)
async def value_error_exception_handler(request: Request, exc: ValueError):
    logger.warning(f"Value error for {request.method} {request.url.path}: {exc}")
    return JSONResponse(status_code=400, content={"status_code": "400", "path": request.url.path, "message": str(exc)})


@app.exception_handler(ResourceNotFoundException)
async def resource_not_found_exception_handler(request: Request, exc: ResourceNotFoundException):
    logger.warning(f"Resource not found for {request.method} {request.url.path}: {exc}")
    return JSONResponse(status_code=404, content={"status_code": "404", "path": request.url.path, "message": str(exc)})


@app.exception_handler(LIFException)
async def lif_exception_handler(request: Request, exc: LIFException):
    return default_exception_handler(request, exc)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return default_exception_handler(request, exc)


def default_exception_handler(request: Request, exc: Exception):
    random_uuid = uuid4()
    logger.error(f"[{random_uuid}] Error occurred for {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "status_code": "500",
            "path": request.url.path,
            "message": "Internal server error. Please try again later.",
            "code": str(random_uuid),
        },
    )
