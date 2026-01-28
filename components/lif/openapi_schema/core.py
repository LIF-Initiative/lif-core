"""OpenAPI schema provider.

This component is responsible for sourcing the OpenAPI document that defines the
dynamic model fields. It integrates with the MDR client as the primary source,
and falls back to a local file (primarily for development and tests).

Public API:
- get_schema_fields() -> List[SchemaField]

Configuration (envvars):
- LIF_OPENAPI_SCHEMA_PATH: Optional file path fallback to read JSON.
- LIF_OPENAPI_ROOT: Optional root schema name (e.g., "Person").
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from lif.datatypes.schema import SchemaField
from lif.logging.core import get_logger
from lif.schema.core import load_schema_nodes
import lif.mdr_client.core as mdr_core

logger = get_logger(__name__)


def _load_from_file(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"OpenAPI schema file not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in schema file {p}: {e}")


def get_schema_fields() -> List[SchemaField]:
    """Return SchemaField list sourced from MDR client or file based on env configuration.

    Resolution order:
    1) Attempt to load OpenAPI from MDR via get_openapi_lif_data_model()
    2) Else if LIF_OPENAPI_SCHEMA_PATH is set, load from file
    """
    # Root resolution (optional); can be provided from env
    root = os.getenv("LIF_OPENAPI_ROOT") or os.getenv("ROOT_NODE") or "Person"

    print(f"Root node for schema fields: {root}")

    # Preferred: MDR client provider
    try:
        logger.info("Loading OpenAPI schema via MDR client")
        doc = mdr_core.get_openapi_lif_data_model()
        return load_schema_nodes(doc, root)
    except Exception as e:  # noqa: BLE001 - surface clean fallback path
        logger.warning("MDR client schema load failed: %s. Falling back...", e)

    # Fallback: file path provider
    path = os.getenv("LIF_OPENAPI_SCHEMA_PATH")
    if path:
        logger.info("Loading OpenAPI schema from file: %s", path)
        doc = _load_from_file(path)
        return load_schema_nodes(doc, root)

    raise RuntimeError(
        "No OpenAPI schema source configured. Provide MDR client implementation, "
        "or set LIF_OPENAPI_SCHEMA_PATH."
    )
