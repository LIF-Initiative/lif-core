import datetime as dt
import json
import os
import re
import requests

from lif.datatypes import LIFFragment, LIFQueryPlanPart, OrchestratorJobQueryPlanPartResults
from lif.logging import get_logger
from ..core import LIFAdapterType, LIFDataSourceAdapter


logger = get_logger(__name__)


class LIFToLIFAdapter(LIFDataSourceAdapter):
    """Adapter that converts LIF data to LIF data (no-op)."""

    adapter_id = "lif-to-lif"
    adapter_type = LIFAdapterType.LIF_TO_LIF
    credential_keys = ["host", "scheme", "token"]

    def __init__(self, lif_query_plan_part: LIFQueryPlanPart, credentials: dict):
        self.lif_query_plan_part = lif_query_plan_part
        self.host = credentials.get("host")
        self.scheme = credentials.get("scheme") or "https"
        self.token = credentials.get("token")

    def run(self) -> OrchestratorJobQueryPlanPartResults:
        graphql_url = f"{self.scheme}://{self.host}/graphql"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": f"LIF-Adapter-{self.adapter_id}",
        }

        ident = self.lif_query_plan_part.person_id.identifier or ""
        # Map human-readable identifierType to GraphQL enum token
        raw_ident_type = self.lif_query_plan_part.person_id.identifierType or ""
        ident_type_value = re.sub(r"[^A-Za-z0-9]+", "_", raw_ident_type).upper()
        ident_type_value = re.sub(r"__+", "_", ident_type_value).strip("_")

        # TODO: Add dynamic GraphQL query generation from lif fragments
        # Choose GraphQL file based on adapter identifier
        info_source_id = self.lif_query_plan_part.information_source_id.lower()
        base_dir = os.path.dirname(__file__)
        if "org_2" in info_source_id or "org2" in info_source_id:
            query_filename = "graphql_query_all_fields_org2.graphql"
        elif "org_3" in info_source_id or "org3" in info_source_id:
            query_filename = "graphql_query_all_fields_org3.graphql"
        else:
            raise ValueError(
                f"Unknown information source ID: {info_source_id}. Expected IDs containing org_2, org2, org_3, or org3."
            )
        query_path = os.path.join(base_dir, query_filename)

        with open(query_path, "r", encoding="utf-8") as f:
            query_text = f.read()
        logger.info(f"Loaded GraphQL query from: {query_filename}")

        payload = {
            "operationName": "GetPersonByIdentifier",
            "query": query_text,
            "variables": {"identifier": ident, "identifierType": ident_type_value},
        }

        logger.debug(f"GraphQL payload: {json.dumps(payload, indent=2)}")

        response = requests.post(graphql_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()

        if "errors" in result:
            error_msg = f"GraphQL errors: {result['errors']}"
            logger.error(error_msg)
            raise Exception(error_msg)

        response_data = result.get("data", {})
        output = {
            "person_id": {
                "identifier": self.lif_query_plan_part.person_id.identifier,
                "identifierType": self.lif_query_plan_part.person_id.identifierType,
            },
            "fragments": [{"fragment_path": "person.all", "fragment": [response_data]}],
        }

        output = OrchestratorJobQueryPlanPartResults(
            information_source_id=self.lif_query_plan_part.information_source_id,
            adapter_id=self.lif_query_plan_part.adapter_id,
            data_timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            person_id=self.lif_query_plan_part.person_id,
            fragments=[LIFFragment(fragment_path="person.all", fragment=[response_data])],
            error=None,
        )

        logger.info("GraphQL query executed successfully")
        logger.debug(f"Response data: {response_data}")

        return output
