from httpx import AsyncClient

HEADER_MDR_API_KEY = {"X-API-Key": "changeme1"}


async def create_translation(
    *,
    async_client_translator: AsyncClient,
    source_data_model_id: str,
    target_data_model_id: str,
    json_to_translate: dict,
    headers: dict = HEADER_MDR_API_KEY,
) -> dict:
    """
    Helper function to create/run a translation between source and target data models.

    Args:
        async_client_translator: An instance of AsyncClient to make HTTP requests to the Translator API
        source_data_model_id: The ID of the source data model
        target_data_model_id: The ID of the target data model
        json_to_translate: The JSON data to be translated
        headers: Optional headers to include in the request (default is HEADER_MDR_API_KEY)

    Returns:
        The translated json
    """

    translate_response = await async_client_translator.post(
        f"/translate/source/{source_data_model_id}/target/{target_data_model_id}",
        headers=headers,
        json=json_to_translate,
    )
    assert translate_response.status_code == 200, (
        str(translate_response.status_code) + str(translate_response.text) + str(translate_response.headers)
    )
    return translate_response.json()
