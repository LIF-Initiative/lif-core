import requests

from lif.datatypes import LIFQueryPlanPart
from lif.logging import get_logger
from lif.data_source_adapters.core import LIFAdapterType, LIFDataSourceAdapter


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

        # The host only: the URL ends in the person identifier.
        logger.info(f"Example Data Source REST API request to {self.scheme}://{self.host}")

        response = requests.get(source_url, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()

        if "errors" in result:
            errors = result["errors"]
            # A count only: a source can echo the requested identifier back in its error messages.
            logger.error(
                f"Example Data Source REST API returned errors (count: {len(errors) if isinstance(errors, list) else 'unknown'})"
            )
            raise Exception(f"Example Data Source REST API errors: {errors}")

        logger.info("Example Data Source REST API query executed successfully")
        logger.debug(f"Response JSON keys: {sorted(result) if isinstance(result, dict) else type(result).__name__}")
        return result
