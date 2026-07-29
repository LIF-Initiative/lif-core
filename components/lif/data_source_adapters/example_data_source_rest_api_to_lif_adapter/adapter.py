import requests

from lif.datatypes import LIFQueryPlanPart
from lif.logging import get_logger
from ..core import LIFAdapterType, LIFDataSourceAdapter


logger = get_logger(__name__)


class ExampleDataSourceRestAPIToLIFAdapter(LIFDataSourceAdapter):
    """Adapter that gathers data from the Example Data Source REST API for LIF to use (no translation in the adapter)."""

    adapter_id = "example-data-source-rest-api-to-lif"
    adapter_type = LIFAdapterType.PIPELINE_INTEGRATED
    credential_keys = ["host", "scheme", "token"]

    def __init__(self, lif_query_plan_part: LIFQueryPlanPart, credentials: dict):
        self.lif_query_plan_part = lif_query_plan_part
        self.host = credentials.get("host")
        self.scheme = credentials.get("scheme") or "https"
        self.token = credentials.get("token")

    def run(self) -> dict:
        headers = {"x-key": self.token}

        ident = self.lif_query_plan_part.person_id.identifier or ""

        source_url = f"{self.scheme}://{self.host}/r1-demo/users/{ident}"  # f"/graphql"

        logger.info(f"Example Data Source REST API URL: {source_url}")

        response = requests.get(source_url, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()

        if "errors" in result:
            error_msg = f"Example Data Source REST API errors: {result['errors']}"
            logger.error(error_msg)
            raise Exception(error_msg)

        logger.info("Example Data Source REST API query executed successfully")
        logger.debug(f"Response JSON: {result}")
        return result
