import asyncio
import httpx
import os
import types
import pytest
from unittest import mock
from unittest.mock import patch, MagicMock

from lif.exceptions.core import ResourceNotFoundException
from lif.mdr_client import core


def test_sample():
    assert core is not None


def test_get_openapi_lif_data_model_from_file():
    data_model = core.get_openapi_lif_data_model_from_file()
    _assert_openapi_data_model_results_from_file(data_model)


@patch("httpx.AsyncClient.get")
@mock.patch.dict(
    os.environ,
    {
        "USE_OPENAPI_DATA_MODEL_FROM_FILE": "true",
        "LIF_MDR_API_URL": "http://api.example.com",
        "OPENAPI_DATA_MODEL_ID": "123",
    },
)
async def test_get_openapi_lif_data_model_with_config_to_use_file(mock_get_schema):
    data_model = await core.get_openapi_lif_data_model()
    _assert_openapi_data_model_results_from_file(data_model)
    mock_get_schema.assert_not_called()


@patch("httpx.AsyncClient.get")
@mock.patch.dict(
    os.environ,
    {
        "USE_OPENAPI_DATA_MODEL_FROM_FILE": "false",
        "LIF_MDR_API_URL": "http://api.example.com",
        "OPENAPI_DATA_MODEL_ID": "123",
    },
)
async def test_get_openapi_lif_data_model_fallback_on_error(mock_get_schema):
    mock_get_schema.side_effect = httpx.HTTPStatusError(
        "Error", request=httpx.Request("GET", "http://api.example.com"), response=MagicMock(status_code=500)
    )
    data_model = await core.get_openapi_lif_data_model()
    mock_get_schema.assert_called_once()
    _assert_openapi_data_model_results_from_file(data_model)


@patch("httpx.AsyncClient.get")
@mock.patch.dict(
    os.environ,
    {
        "USE_OPENAPI_DATA_MODEL_FROM_FILE": "false",
        "LIF_MDR_API_URL": "http://api.example.com",
        "OPENAPI_DATA_MODEL_ID": "123",
    },
)
async def test_get_openapi_lif_data_model_with_config_to_call_mdr(mock_get_schema):
    full_openapi_url = (
        "http://api.example.com/datamodels/open_api_schema/123?include_attr_md=true&include_entity_md=false"
    )
    mock_response = _create_mock_response(200, {"openapi": "3.0.0", "components": {"schemas": {}}}, full_openapi_url)
    mock_get_schema.return_value = mock_response

    async def run_test():
        data_model = await core.get_openapi_lif_data_model()
        _assert_openapi_data_model_results_from_mdr(data_model)

    await run_test()
    mock_get_schema.assert_called_once_with(full_openapi_url, headers={"X-API-Key": "no_auth_token_set"})


@patch("httpx.AsyncClient.get")
@mock.patch.dict(os.environ, {"LIF_MDR_API_URL": "http://api.example.com", "OPENAPI_DATA_MODEL_ID": "123"})
async def test_get_openapi_lif_data_model_from_mdr_with_no_use_openapi_from_file_flag_value_specified(mock_get_schema):
    full_openapi_url: str = (
        "http://api.example.com/datamodels/open_api_schema/123?include_attr_md=true&include_entity_md=false"
    )
    mock_response = _create_mock_response(200, {"openapi": "3.0.0", "components": {"schemas": {}}}, full_openapi_url)
    mock_get_schema.return_value = mock_response

    async def run_test():
        data_model = await core.get_openapi_lif_data_model()
        _assert_openapi_data_model_results_from_mdr(data_model)

    await run_test()
    mock_get_schema.assert_called_once_with(full_openapi_url, headers={"X-API-Key": "no_auth_token_set"})


@patch("httpx.AsyncClient.get")
@mock.patch.dict(os.environ, {"USE_OPENAPI_DATA_MODEL_FROM_FILE": "false", "LIF_MDR_API_URL": "http://api.example.com"})
async def test_get_openapi_lif_data_model_from_mdr_with_no_openapi_data_model_id_specified_fallback(mock_get_schema):
    mock_response = _create_mock_response(
        200, {"openapi": "3.0.0"}, "http://api.example.com/datamodels/open_api_schema/123"
    )
    mock_get_schema.return_value = mock_response

    async def run_test():
        data_model = await core.get_openapi_lif_data_model()
        _assert_openapi_data_model_results_from_file(data_model)

    await run_test()
    mock_get_schema.assert_not_called()


@patch("httpx.AsyncClient.get")
@mock.patch.dict(os.environ, {"LIF_MDR_API_URL": "http://api.example.com"})
@pytest.mark.asyncio
async def test_get_data_model_schema(mock_get):
    mock_response = _create_mock_response(
        200,
        {"openapi": "3.0.0"},
        "http://api.example.com/datamodels/open_api_schema/123?include_attr_md=false&include_entity_md=false",
    )
    mock_get.return_value = mock_response

    async def run_test():
        schema = await core.get_data_model_schema("123")
        assert isinstance(schema, dict)
        assert "openapi" in schema
        assert schema["openapi"] == "3.0.0"

    await run_test()
    assert mock_get.called
    assert mock_get.call_count == 1
    assert (
        mock_get.call_args[0][0]
        == "http://api.example.com/datamodels/open_api_schema/123?include_attr_md=false&include_entity_md=false"
    )


@patch("httpx.AsyncClient.get")
@mock.patch.dict(os.environ, {"LIF_MDR_API_URL": "http://api.example.com"})
@pytest.mark.asyncio
async def test_get_data_model_schema_with_flags(mock_get):
    mock_response = _create_mock_response(
        200,
        {"openapi": "3.0.0"},
        "http://api.example.com/datamodels/open_api_schema/123?include_attr_md=true&include_entity_md=true",
    )
    mock_get.return_value = mock_response

    async def run_test():
        schema = await core.get_data_model_schema("123", include_attr_md=True, include_entity_md=True)
        assert isinstance(schema, dict)
        assert "openapi" in schema
        assert schema["openapi"] == "3.0.0"

    await run_test()
    assert mock_get.called
    assert mock_get.call_count == 1
    assert (
        mock_get.call_args[0][0]
        == "http://api.example.com/datamodels/open_api_schema/123?include_attr_md=true&include_entity_md=true"
    )


@patch("httpx.AsyncClient.get")
def test_get_data_model_schema_not_found(mock_get):
    mock_response = _create_mock_response(
        404, {"detail": "Data Model not found"}, "https://api.example.com/datamodels/open_api_schema/999"
    )
    mock_get.return_value = mock_response

    async def run_test():
        await core.get_data_model_schema("999")

    with pytest.raises(ResourceNotFoundException) as exc_info:
        asyncio.run(run_test())
    assert "Data model with ID 999 not found in MDR." in str(exc_info.value)


@patch("httpx.AsyncClient.get")
def test_get_data_model_transformation(mock_get):
    mock_response = _create_mock_response(
        200,
        {"total": 1, "data": [{"TransformationExpression": "person.name = name"}]},
        "https://api.example.com/transformation_groups/transformations_for_data_models/?source_data_model_id=25&target_data_model_id=17",
    )
    mock_get.return_value = mock_response

    async def run_test():
        transformation = await core.get_data_model_transformation("25", "17")
        assert isinstance(transformation, dict)
        assert "total" in transformation
        assert transformation["total"] == 1
        assert "data" in transformation
        assert isinstance(transformation["data"], list)
        assert len(transformation["data"]) == 1
        assert transformation["data"][0]["TransformationExpression"] == "person.name = name"

    asyncio.run(run_test())


@patch("httpx.AsyncClient.get")
def test_get_data_model_transformation_no_results_workaround(mock_get):
    mock_response = _create_mock_response(
        200,
        {"total": 0, "data": []},
        "https://api.example.com/transformation_groups/transformations_for_data_models/?source_data_model_id=25&target_data_model_id=17",
    )
    mock_get.return_value = mock_response

    async def run_test():
        await core.get_data_model_transformation("25", "17")

    with pytest.raises(ResourceNotFoundException) as exc_info:
        asyncio.run(run_test())
    assert "Transformation from 25 to 17 not found in MDR." in str(exc_info.value)


@patch("httpx.AsyncClient.get")
def test_get_data_model_transformation_not_found(mock_get):
    mock_response = _create_mock_response(
        404,
        {"detail": "Transformation not found"},
        "https://api.example.com/transformation_groups/transformations_for_data_models/?source_data_model_id=25&target_data_model_id=17",
    )
    mock_get.return_value = mock_response

    async def run_test():
        await core.get_data_model_transformation("25", "17")

    with pytest.raises(ResourceNotFoundException) as exc_info:
        asyncio.run(run_test())
    assert "Transformation from 25 to 17 not found in MDR." in str(exc_info.value)


@patch("httpx.AsyncClient.get")
async def test_get_transformation_groups_from_mdr_success(mock_get):
    config = types.SimpleNamespace(mdr_api_url="http://api.example.com", mdr_api_auth_token="secret-token")
    url = "http://api.example.com/transformation_groups/"
    payload = {"total": 1, "data": [{"TargetDataModelId": 2, "GroupVersion": "1.0"}]}
    mock_get.return_value = _create_mock_response(200, payload, url)

    result = await core.get_transformation_groups_from_mdr(config=config, source_data_model_id="17")

    assert result == payload
    mock_get.assert_called_once()
    # URL is the bare path; query args are passed via params (httpx encodes them).
    assert mock_get.call_args.args[0] == url
    assert mock_get.call_args.kwargs["params"] == {
        "source_data_model_id": "17",
        "exportable": True,
        "pagination": False,
        "size": 100,
    }
    # Auth token is sourced from config, not the environment.
    assert mock_get.call_args.kwargs["headers"]["X-API-Key"] == "secret-token"


@patch("httpx.AsyncClient.get")
async def test_get_transformation_groups_from_mdr_raises_on_http_error(mock_get):
    config = types.SimpleNamespace(mdr_api_url="http://api.example.com", mdr_api_auth_token="secret-token")
    mock_get.return_value = _create_mock_response(
        500, {"detail": "boom"}, "http://api.example.com/transformation_groups/"
    )

    with pytest.raises(core.MDRClientException):
        await core.get_transformation_groups_from_mdr(config=config, source_data_model_id="17")


def _create_mock_response(status_code: int, json_data, uri: str):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data
    if status_code >= 400:
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=httpx.Request("GET", uri), response=mock_response
        )
    else:
        mock_response.raise_for_status.return_value = None
    return mock_response


def _assert_openapi_data_model_results_from_file(data_model: dict):
    assert isinstance(data_model, dict)
    assert "openapi" in data_model
    assert "components" in data_model
    assert "schemas" in data_model["components"]
    assert data_model["openapi"] == "3.0.0"
    assert data_model["components"]["schemas"] != {}
    assert "Person" in data_model["components"]["schemas"]
    assert "OrganizationCode" in data_model["components"]["schemas"]


def _assert_openapi_data_model_results_from_mdr(data_model: dict):
    assert isinstance(data_model, dict)
    assert "openapi" in data_model
    assert "components" in data_model
    assert "schemas" in data_model["components"]
    assert data_model["openapi"] == "3.0.0"
    assert data_model["components"]["schemas"] == {}
