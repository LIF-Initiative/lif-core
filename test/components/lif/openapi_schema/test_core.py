import os
import json
from unittest.mock import patch

import pytest

from lif.openapi_schema.core import get_schema_fields


def test_get_schema_fields_from_file(tmp_path):
    # Create a temporary OpenAPI file
    doc = {
        "openapi": "3.0.0",
        "components": {"schemas": {"Person": {"type": "object", "properties": {"Name": {"type": "string"}}}}},
    }
    p = tmp_path / "openapi.json"
    p.write_text(json.dumps(doc), encoding="utf-8")

    with patch.dict(os.environ, {"LIF_OPENAPI_SCHEMA_PATH": str(p), "LIF_OPENAPI_ROOT": "Person"}, clear=True):
        fields = get_schema_fields()
        assert any(f.json_path.lower().startswith("person") for f in fields)


def test_get_schema_fields_from_mdr(monkeypatch):
    # Patch MDR client to return a small OpenAPI doc
    def fake_get_openapi_lif_data_model():
        return {
            "openapi": "3.0.0",
            "components": {"schemas": {"Person": {"type": "object", "properties": {"Name": {"type": "string"}}}}},
        }

    with patch("lif.mdr_client.core.get_openapi_lif_data_model", fake_get_openapi_lif_data_model):
        with patch.dict(os.environ, {"LIF_OPENAPI_ROOT": "Person"}, clear=True):
            fields = get_schema_fields()
            assert any(f.json_path.lower().startswith("person") for f in fields)


def test_get_schema_fields_legacy(tmp_path):
    # Uses repo test_data path convention
    with patch.dict(os.environ, {"OPENAPI_SCHEMA_FILE": "test_openapi_schema.json", "ROOT_NODE": "Person"}, clear=True):
        fields = get_schema_fields()
        assert any(f.json_path.lower().startswith("person") for f in fields)


def test_no_configuration_raises():
    # Patch MDR to raise, and no fallbacks set
    def fake_get_openapi_lif_data_model():
        raise RuntimeError("mdr unavailable")

    with patch("lif.mdr_client.core.get_openapi_lif_data_model", fake_get_openapi_lif_data_model):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError):
                get_schema_fields()
