import json
import os
from unittest import mock
from unittest.mock import patch
from lif.api_graphql import core
from lif.mdr_client import get_openapi_lif_data_model


def test_sample():
    assert core is not None


@patch("httpx.AsyncClient.post")
@mock.patch.dict(os.environ, {"LIF_GRAPHQL_ROOT_TYPE_NAME": "Person", "USE_OPENAPI_DATA_MODEL_FROM_FILE": "true"})
async def test_fetch_dynamic_graphql_schema(mock_post):
    query: str = """
        query MyQuery {
            person(
                filter: {Identifier: {identifier: "100006", identifierType: "SCHOOL_ASSIGNED_NUMBER"}}
            ) {
                Identifier {
                    identifier
                    identifierType
                }
                EmploymentPreferences {
                    organizationTypes
                }
            }
        }
    """

    results_json: str = """
        [
            {
                "person": [
                    {
                        "Identifier": [
                            {
                                "identifier": "100006",
                                "identifierType": "SCHOOL_ASSIGNED_NUMBER"
                            }
                        ],
                        "EmploymentPreferences": [
                            {
                                "organizationTypes": [
                                    "Non-Profit",
                                    "Public Sector"
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    """

    results = json.loads(results_json)
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = results
    mock_post.return_value = mock_response

    async def run_test():
        openapi = await get_openapi_lif_data_model()
        schema = await core.fetch_dynamic_graphql_schema(openapi=openapi)
        # print("Generated Schema: ", schema)
        assert schema is not None
        execution_result = await schema.execute(query)
        assert execution_result.errors is None
        assert execution_result.data is not None
        # print("Execution Result Data: ", execution_result.data)
        assert len(execution_result.data["person"]) == 1
        assert len(execution_result.data["person"][0]["Identifier"]) == 1
        assert len(execution_result.data["person"][0]["EmploymentPreferences"]) == 1
        assert execution_result.data["person"][0]["Identifier"][0]["identifier"] == "100006"
        assert execution_result.data["person"][0]["EmploymentPreferences"][0]["organizationTypes"] == [
            "Non-Profit",
            "Public Sector",
        ]

    await run_test()
