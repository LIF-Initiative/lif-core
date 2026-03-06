from copy import deepcopy
from typing import List
from jsonata import jsonata
from jsonschema import validate, ValidationError
from pydantic import BaseModel, Field

from lif.logging.core import get_logger
from lif.mdr_client.core import get_data_model_schema, get_data_model_transformation
from lif.translator.utils import convert_transformation_to_mappings, deep_merge

logger = get_logger(__name__)


class BaseTranslatorConfig(BaseModel):
    source_schema: dict = Field(..., description="The JSON schema of the source data")
    target_schema: dict = Field(..., description="The JSON schema of the target data")
    mappings: List[str] = Field(..., description="List of transformation expressions")


class BaseTranslator:
    def __init__(self, config: BaseTranslatorConfig):
        self.config = config
        self.source_schema = config.source_schema
        self.target_schema = config.target_schema
        self.mappings = config.mappings

    def run(self, input: dict) -> dict:
        # validate input against source schema
        self._validate_against_schema(data=input, schema=self.source_schema)

        # apply mapping expressions to transform input to target schema
        result: dict = {}

        for mapping_expression_str in self.mappings:
            try:
                mapping_expression = jsonata.Jsonata(mapping_expression_str)
                fragment = mapping_expression.evaluate(input)
                logger.info("Mapping: %s", mapping_expression_str)
                logger.info("Fragment: %s", fragment)
            except Exception as e:
                logger.warning("Skipping mapping due to evaluation error: %s", e)
                continue

            # Only merge object-shaped fragments; ignore scalars/None
            if not isinstance(fragment, dict):
                logger.warning("Skipping non-object fragment: %r", fragment)
                continue

            # Tentative merge -> validate -> commit or rollback
            tentative = deepcopy(result)
            deep_merge(tentative, fragment)

            try:
                # If you want to be strict about *partial* validity, validate after each merge:
                self._validate_against_schema(data=tentative, schema=self.target_schema)
                result = tentative
            except ValueError as e:
                logger.warning("Discarding fragment due to target schema violation: %s", e)
                # do not apply this fragment
                continue

        # final validation (should already be valid if the per-fragment check is kept)
        self._validate_against_schema(data=result, schema=self.target_schema)

        logger.info("Translation result: %s", result)
        return result

    def _validate_against_schema(self, data: dict, schema: dict):
        try:
            validate(instance=data, schema=schema)
        except ValidationError as e:
            raise ValueError(f"Data does not conform to schema: {e.message}")


class TranslatorConfig(BaseModel):
    source_schema_id: str = Field(..., description="The identifier of the source schema")
    target_schema_id: str = Field(..., description="The identifier of the target schema")


class Translator:
    def __init__(self, config: TranslatorConfig):
        self.source_schema_id = config.source_schema_id
        self.target_schema_id = config.target_schema_id

    async def run(self, input: dict) -> dict:
        source_schema = await self._fetch_schema(self.source_schema_id)
        target_schema = await self._fetch_schema(self.target_schema_id)

        transformation = await self._fetch_transformation(self.source_schema_id, self.target_schema_id)
        logger.info("Transformation: %s", transformation)
        mappings = convert_transformation_to_mappings(transformation)

        base_translator_config = BaseTranslatorConfig(
            source_schema=source_schema, target_schema=target_schema, mappings=mappings
        )
        base_translator = BaseTranslator(config=base_translator_config)
        result = base_translator.run(input)

        return result

    async def _fetch_schema(self, schema_id: str) -> dict:
        return await get_data_model_schema(schema_id, include_attr_md=True, include_entity_md=False)

    async def _fetch_transformation(self, source_schema_id: str, target_schema_id: str) -> dict:
        return await get_data_model_transformation(source_schema_id, target_schema_id)
