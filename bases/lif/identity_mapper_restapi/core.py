from contextlib import asynccontextmanager
from typing import List
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker, Session

from lif.datatypes import IdentityMapping
from lif.exceptions.core import DataNotFoundException, LIFException
from lif.identity_mapper_service.core import IdentityMapperService
from lif.identity_mapper_storage.core import IdentityMapperStorage
from lif.identity_mapper_storage_sql.core import IdentityMapperSqlStorage
from lif.identity_mapper_storage_sql.db import dispose_db_engine, get_db_session_factory, initialize_database
from lif.logging.core import get_logger


storage: IdentityMapperStorage | None = None
service: IdentityMapperService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize()
    yield
    shutdown()


def initialize():
    initialize_database()
    session_factory: sessionmaker[Session] = get_db_session_factory()
    global storage
    global service
    storage = IdentityMapperSqlStorage(session_factory)
    service = IdentityMapperService(storage=storage)


def shutdown():
    dispose_db_engine()


app = FastAPI(lifespan=lifespan)
logger = get_logger(__name__)
logger.info("Identity Mapper REST API service initialized successfully")


@app.post(
    "/organizations/{org_id}/persons/{person_id}/mappings",
    status_code=status.HTTP_200_OK,
    response_model=List[IdentityMapping],
)
async def do_save_mappings(org_id: str, person_id: str, mappings: List[IdentityMapping]) -> List[IdentityMapping]:
    logger.info(f"CALL RECEIVED TO (POST) /organizations/{org_id}/persons/{person_id}/mappings API")
    if service is None:
        raise RuntimeError("Service is not initialized")
    mappings_created: List[IdentityMapping] = await service.save_mappings(org_id, person_id, mappings)
    logger.info(f"Mappings saved successfully for person {person_id} in organization {org_id}")
    return mappings_created


@app.get(
    "/organizations/{org_id}/persons/{person_id}/mappings",
    status_code=status.HTTP_200_OK,
    response_model=List[IdentityMapping],
)
async def do_get_mappings(org_id: str, person_id: str) -> List[IdentityMapping]:
    logger.info(f"CALL RECEIVED TO (GET) /organizations/{org_id}/persons/{person_id}/mappings API")
    if service is None:
        raise RuntimeError("Service is not initialized")
    mappings = await service.get_mappings(org_id, person_id)
    logger.info(f"Mappings retrieved successfully for person {person_id} in organization {org_id}")
    return mappings


@app.delete("/organizations/{org_id}/persons/{person_id}/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def do_delete_mapping(org_id: str, person_id: str, mapping_id: str):
    logger.info(f"CALL RECEIVED TO (DELETE) /organizations/{org_id}/persons/{person_id}/mappings/{mapping_id} API")
    if service is None:
        raise RuntimeError("Service is not initialized")
    await service.delete_mapping(org_id, person_id, mapping_id)
    logger.info(f"Mapping {mapping_id} deleted successfully for person {person_id} in organization {org_id}")


@app.exception_handler(DataNotFoundException)
async def data_not_found_exception_handler(request: Request, exc: DataNotFoundException):
    logger.warning(f"Data not found for {request.method} {request.url.path}: {exc}")
    return JSONResponse(status_code=404, content={"status_code": "404", "path": request.url.path, "message": str(exc)})


@app.exception_handler(ValueError)
async def value_error_exception_handler(request: Request, exc: ValueError):
    logger.warning(f"Value error for {request.method} {request.url.path}: {exc}")
    return JSONResponse(status_code=400, content={"status_code": "400", "path": request.url.path, "message": str(exc)})


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
