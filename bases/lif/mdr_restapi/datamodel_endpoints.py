import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from lif.datatypes.mdr_sql_model import AccessType, StateType
from lif.mdr_dto.datamodel_dto import CreateDataModelDTO, DataModelDTO, DataModelWithDetailsDTO, UpdateDataModelDTO
from lif.mdr_services import datamodel_service, schema_generation_service, schema_upload_service, tag_service
from lif.mdr_utils.database_setup import get_session
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = get_logger(__name__)


@router.get("/", response_model=Dict[str, Any])
async def read_datamodels(
    request: Request,  # Add the Request object to construct URLs
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),  # Default to page 1
    size: int = Query(10, ge=1),  # Default to 10 items per page
    pagination: bool = True,
    level_of_access: AccessType = None,
    state: StateType = None,
    include_extension: bool = True,
):
    # Calculate offset
    offset = (page - 1) * size

    # Call the service function to get total count and paginated results
    total_count, datamodels = await datamodel_service.get_paginated_datamodels(
        session,
        offset,
        size,
        pagination=pagination,
        level_of_access=level_of_access,
        state=state,
        include_extension=include_extension,
    )

    if pagination:
        # Calculate total pages
        total_pages = (total_count + size - 1) // size

        # Generate next and previous links
        base_url = str(request.url).split("?")[0]
        next_url = f"{base_url}?page={page + 1}&size={size}" if page < total_pages else None
        previous_url = f"{base_url}?page={page - 1}&size={size}" if page > 1 else None

        return {
            "total": total_count,
            "page": page,
            "size": size,
            "total_pages": total_pages,
            "next": next_url,
            "previous": previous_url,
            "data": datamodels,
        }

    return {"total": total_count, "data": datamodels}


@router.get("/{datamodel_id}", response_model=DataModelDTO)
async def get_datamodel(datamodel_id: int, session: AsyncSession = Depends(get_session)):
    datamodel = await datamodel_service.get_datamodel_by_id(session, datamodel_id)
    return datamodel


@router.get("/with_details/{datamodel_id}", response_model=DataModelWithDetailsDTO)
async def get_datamodel(
    datamodel_id: int,
    session: AsyncSession = Depends(get_session),
    partner_only: bool = False,
    org_ext_only: bool = False,
    public_only: bool = False,
):
    datamodel = await datamodel_service.get_datamodel_with_details_by_id(
        session, datamodel_id, partner_only=partner_only, org_ext_only=org_ext_only, public_only=public_only
    )
    return datamodel


@router.get("/by_entity_id/{entity_id}", response_model=DataModelDTO)
async def get_datamodel(entity_id: int, session: AsyncSession = Depends(get_session)):
    datamodel = await datamodel_service.get_datamodel_by_entity_id(session, entity_id)
    return datamodel


@router.post("/", response_model=DataModelDTO, status_code=status.HTTP_201_CREATED)
async def create_datamodel(
    request: Request, data: CreateDataModelDTO, response: Response, session: AsyncSession = Depends(get_session)
):
    # current_user will contain the username from the JWT token
    logger.info(f"User {request.state.principal} is creating a datamodel")
    datamodel = await datamodel_service.create_datamodel(session, data)
    # Set the Location header
    response.headers["Location"] = f"/datamodels/{datamodel.Id}"
    return datamodel


@router.put("/{datamodel_id}", response_model=DataModelDTO)
async def update_datamodel(datamodel_id: int, data: UpdateDataModelDTO, session: AsyncSession = Depends(get_session)):
    datamodel = await datamodel_service.update_datamodel(session, datamodel_id, data)
    return datamodel


@router.put("/{datamodel_id}/use_schema_upload", response_model=DataModelDTO)
async def update_datamodel_with_upload(
    datamodel_id: int,
    file: UploadFile = File(
        ..., description="OpenAPI schema JSON file previously downloaded via the GET open_api_schema endpoint"
    ),
    session: AsyncSession = Depends(get_session),
    data_model_name: Optional[str] = Form(None, description="Name of the data model being updated"),
    data_model_version: Optional[str] = Form(None, description="Version of the data model being updated"),
    data_model_description: Optional[str] = Form(None, description="Description of the data model being updated"),
    use_considerations: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    activation_date: Optional[datetime] = Form(None, description="Activation date for the data model (ISO 8601)"),
    deprecation_date: Optional[datetime] = Form(None, description="Deprecation date for the data model (ISO 8601)"),
    contributor: Optional[str] = Form(None, description="Name of the contributor"),
    contributor_organization: Optional[str] = Form(None, description="Name of the contributor organization"),
    state: Optional[str] = Form("Draft", description="Initial state of the data model"),
    tags: Optional[str] = Form(None, description="Comma-separated list of tags to associate with the data model"),
):
    metadata = UpdateDataModelDTO(
        Name=data_model_name,
        DataModelVersion=data_model_version,
        Description=data_model_description,
        UseConsiderations=use_considerations,
        Notes=notes,
        ActivationDate=activation_date,
        DeprecationDate=deprecation_date,
        Contributor=contributor,
        ContributorOrganization=contributor_organization,
        State=state,
        Tags=tags,
    )

    """Upload an OpenAPI schema JSON exported from the system along with metadata to update a new data model."""
    if file.content_type not in ("application/json", "text/json", None):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="File must be JSON (application/json)"
        )
    try:
        # Consider pulling out into a component function.
        raw_bytes = await file.read()
        if not raw_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
        try:
            schema_dict = json.loads(raw_bytes.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON: {e}") from e

        datamodel = await datamodel_service.update_datamodel(session, datamodel_id, metadata, schema_dict)

        return datamodel
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error while uploading OpenAPI schema")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{datamodel_id}", response_model=dict)
async def delete_datamodel(datamodel_id: int, session: AsyncSession = Depends(get_session)):
    return await datamodel_service.soft_delete_data_model(session, datamodel_id)


@router.get("/is_orglif/{datamodel_id}")
async def id_datamodel_extension(datamodel_id: int, session: AsyncSession = Depends(get_session)):
    return await datamodel_service.is_datamodel_orglif(session, datamodel_id)


@router.get("/orglif/", response_model=List[DataModelDTO])
async def get_all_extended_datamodels(
    session: AsyncSession = Depends(get_session), contributor_organization: str = None, state: StateType = None
):
    datamodel = await datamodel_service.get_list_of_orglif_model(
        session=session, contributor_organization=contributor_organization, state=state
    )
    return datamodel


@router.get("/base/{extended_datamodel_id}", response_model=DataModelDTO)
async def get_base_model_for_a_given_extension(
    extended_datamodel_id: int, session: AsyncSession = Depends(get_session)
):
    base_model = await datamodel_service.get_base_model_for_given_extension(session, extended_datamodel_id)
    return base_model


@router.get("/by_ids/", response_model=List[DataModelDTO])
async def get_datamodels_by_ids(
    ids: List[int] = Query(...),  # List of DataModel IDs to fetch
    session: AsyncSession = Depends(get_session),
):
    return await datamodel_service.get_datamodels_by_ids(session, ids)


# @router.get("/{data_model_id}/entities/", response_model=DataModelEntityDTO)
# async def get_attributes_for_entity(data_model_id: int, session: AsyncSession = Depends(get_session)):
#     data_model_entities = await datamodel_service.get_list_of_entities(session, data_model_id)
#     return data_model_entities


@router.get("/open_api_schema/{data_model_id}")
async def get_datamodels_by_ids(
    data_model_id: int,
    session: AsyncSession = Depends(get_session),
    include_attr_md: bool = Query(False),
    include_entity_md: bool = Query(False),
    public_only: bool = Query(False),
    download: bool = Query(False),  # ?download=true to trigger a file download
    full_export: bool = Query(False),
):
    schema = await schema_generation_service.generate_openapi_schema(
        session=session,
        data_model_id=data_model_id,
        include_attr_md=include_attr_md,
        include_entity_md=include_entity_md,
        public_only=public_only,
        full_export=full_export,
    )

    # Normalize to JSON-safe Python objects
    encoded = jsonable_encoder(schema)

    if not download:
        # Normal API response (renders JSON in clients)
        return JSONResponse(content=encoded)

    # Force download as .json
    filename = f"openapi-{data_model_id}.json"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    payload = json.dumps(encoded, indent=2)
    return Response(content=payload, media_type="application/json", headers=headers)


@router.post("/open_api_schema/upload", response_model=DataModelDTO, status_code=status.HTTP_201_CREATED)
async def upload_openapi_schema(
    file: UploadFile = File(
        ..., description="OpenAPI schema JSON file previously downloaded via the GET open_api_schema endpoint"
    ),
    session: AsyncSession = Depends(get_session),
    data_model_name: str = Form(..., description="Name of the data model being created"),
    data_model_version: str = Form(..., description="Version of the data model being created"),
    data_model_description: Optional[str] = Form(None, description="Description of the data model being created"),
    data_model_type: str = Form(..., description="Type of the data model being created"),
    base_data_model_id: Optional[int] = Form(
        None, description="ID of the base data model (usually 1 for Base LIF or null)"
    ),
    use_considerations: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    activation_date: Optional[datetime] = Form(None, description="Activation date for the data model (ISO 8601)"),
    deprecation_date: Optional[datetime] = Form(None, description="Deprecation date for the data model (ISO 8601)"),
    contributor: Optional[str] = Form(None, description="Name of the contributor"),
    contributor_organization: Optional[str] = Form(None, description="Name of the contributor organization"),
    state: Optional[str] = Form("Draft", description="Initial state of the data model"),
    tags: Optional[str] = Form(None, description="Comma-separated list of tags to associate with the data model"),
):
    """Upload an OpenAPI schema JSON exported from the system along with metadata to create a new data model."""
    if file.content_type not in ("application/json", "text/json", None):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="File must be JSON (application/json)"
        )
    try:
        raw_bytes = await file.read()
        if not raw_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
        try:
            schema_dict = json.loads(raw_bytes.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid JSON: {e}") from e

        result = await schema_upload_service.create_data_model_from_openapi_schema(
            session=session,
            openapi_schema=schema_dict,
            data_model_name=data_model_name,
            data_model_version=data_model_version,
            data_model_description=data_model_description,
            data_model_type=data_model_type,
            base_data_model_id=base_data_model_id,
            use_considerations=use_considerations,
            notes=notes,
            activation_date=activation_date,
            deprecation_date=deprecation_date,
            contributor=contributor,
            contributor_organization=contributor_organization,
            state=state,
            tags=tags,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error while uploading OpenAPI schema")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/tags/{data_model_id}", status_code=status.HTTP_201_CREATED)
async def add_tags_for_data_model(
    data_model_id: int, tags: List[str] = Query(...), session: AsyncSession = Depends(get_session)
):
    return await tag_service.add_tags(
        session=session, id=data_model_id, tags=tags, element_type=tag_service.TagElementType.DataModel
    )


@router.delete("/tags/{data_model_id}")
async def delete_tags_for_data_model(
    data_model_id: int, tags: List[str] = Query(...), session: AsyncSession = Depends(get_session)
):
    return await tag_service.delete_tags(
        session=session, id=data_model_id, tags=tags, element_type=tag_service.TagElementType.DataModel
    )


@router.get("/tags/{data_model_id}")
async def get_tags_for_data_model(data_model_id: int, session: AsyncSession = Depends(get_session)):
    return await tag_service.get_tags(
        session=session, id=data_model_id, element_type=tag_service.TagElementType.DataModel
    )
