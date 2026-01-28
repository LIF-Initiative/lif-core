"""
GraphQL backend and resolver helpers.

This module defines a minimal Backend protocol and an HTTP implementation
used by the GraphQL schema factory. It handles payload shapes expected by
the LIF query cache service and returns plain dicts for persons.
"""

# TODO: Figure out if we actually want the annotations directive for this module
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

import httpx

from lif.logging.core import get_logger
from lif.graphql.utils import get_fragments_from_info, get_selected_field_paths, serialize_for_json

logger = get_logger(__name__)


# TODO: Figure out if this backend protocol belongs in this component
class Backend(Protocol):
    async def query(self, filter_dict: Optional[dict], selected_fields: List[str]) -> List[dict]: ...

    async def update(
        self, filter_dict: Optional[dict], input_dict: Optional[dict], selected_fields: List[str]
    ) -> List[dict]: ...


class HttpBackend:
    """HTTP client for the Query Planner endpoints.

    Expects two endpoints:
      - query_url: POST {"filter": {"person": <filter>|None}, "selected_fields": [..]}
      - update_url: POST {"updatePerson": {"filter": {"person": ...}, "input": {...}, "selected_fields": [..]}}
    """

    def __init__(self, query_url: Optional[str], update_url: Optional[str]) -> None:
        self.query_url = query_url
        self.update_url = update_url

    async def _post_json(self, url: Optional[str], payload: dict) -> httpx.Response:
        if not url:
            raise RuntimeError("Backend URL is not configured")
        async with httpx.AsyncClient() as client:
            logger.debug("POST %s payload=%s", url, payload)
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp

    # async def query(self, )

    # TODO: Potentially remove
    async def query(self, filter_dict: Optional[dict], selected_fields: List[str]) -> List[dict]:
        wrapped_filter = {"person": filter_dict} if filter_dict is not None else None
        payload = {"filter": wrapped_filter, "selected_fields": selected_fields}
        resp = await self._post_json(self.query_url, payload)
        raw = resp.json()
        logger.debug("Query response: %s", raw)
        persons: List[dict] = []
        for item in raw or []:
            if isinstance(item, dict):
                val = item.get("person")
                if isinstance(val, list):
                    persons.extend(val)
        return persons

    # TODO: Potentially remove
    async def update(
        self, filter_dict: Optional[dict], input_dict: Optional[dict], selected_fields: List[str]
    ) -> List[dict]:
        wrapped_filter = {"person": filter_dict} if filter_dict is not None else None
        payload = {"updatePerson": {"filter": wrapped_filter, "input": input_dict, "selected_fields": selected_fields}}
        resp = await self._post_json(self.update_url, payload)
        data = resp.json() or {}
        logger.debug("Update response: %s", data)
        persons = data.get("person", [])
        if persons and not isinstance(persons, list):
            persons = [persons]
        return persons or []


def extract_selected_fields(info: Any) -> List[str]:
    """Compute dotted JSON paths actually requested by the client."""
    fragments = get_fragments_from_info(info)
    return get_selected_field_paths(info.field_nodes, fragments, [info.field_name])


def pydantic_inputs_to_dict(
    filter_input: Optional[Any] = None, mutation_input: Optional[Any] = None
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Serialize Strawberry-Pydantic inputs into JSON-safe dicts."""

    def to_dict(obj: Any) -> Optional[Dict[str, Any]]:
        if obj is None:
            return None
        if hasattr(obj, "to_pydantic"):
            return serialize_for_json(obj.to_pydantic())
        if hasattr(obj, "model_dump"):
            return serialize_for_json(obj)
        if isinstance(obj, dict):
            return serialize_for_json(obj)
        return serialize_for_json(obj)

    filter_dict = to_dict(filter_input)
    input_dict = to_dict(mutation_input)
    return filter_dict, input_dict
