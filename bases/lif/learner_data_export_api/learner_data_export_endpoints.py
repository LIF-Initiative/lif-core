from typing import Any, Dict

from fastapi import APIRouter, Request
from lif.datatypes.core import TargetTransformationDataModelDTO, TargetTransformationDataModelsDTO
from lif.mdr_utils.logger_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/exports", response_model=Dict[str, Any])
async def get_data(request: Request):
    """Endpoint to export learner data in a specified format.

    The response model is intentionally generic since it will depend
    on the requested data format and transformation.
    """

    # TODO: Build this out.
    logger.info("Received request for learner data export as %s", request.state.principal)

    return {"total": "data"}


@router.get("/available-data-formats", response_model=TargetTransformationDataModelsDTO)
async def get_available_data_formats(request: Request):
    # TODO: Build this out.
    logger.info("Received request for available data formats as %s", request.state.principal)

    data_formats = TargetTransformationDataModelsDTO(
        metadata={"total": 3},
        DataFormats=[
            TargetTransformationDataModelDTO(
                name="OpenBadges 3.0",
                version="1.0.3",
                contributorOrganization="OB",
                TransformationVersions=["1.0.0", "1.1.0"],
            ),
            TargetTransformationDataModelDTO(
                name="CEDS", version="2.0.0", contributorOrganization="CEDS Org", TransformationVersions=["2.0.0"]
            ),
            TargetTransformationDataModelDTO(
                name="ExampleDataSource",
                version="1.0.1",
                contributorOrganization="Community",
                TransformationVersions=["1.3.0"],
            ),
        ],
    )
    return data_formats
