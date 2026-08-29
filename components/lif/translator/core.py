import os
import threading
from copy import deepcopy
from time import perf_counter
from typing import List

from cachetools import TTLCache
from jsonata import jsonata
from jsonschema import ValidationError, validate
from pydantic import BaseModel, Field

from lif.logging.core import get_logger
from lif.mdr_client.core import get_data_model_schema, get_data_model_transformation
from lif.translator.utils import convert_transformation_to_mappings, deep_merge

logger = get_logger(__name__)

_CACHE_TTL = int(os.environ.get("TRANSLATOR_CACHE_TTL_SECONDS", 300))
_schema_cache: TTLCache = TTLCache(maxsize=128, ttl=_CACHE_TTL)
_transformation_cache: TTLCache = TTLCache(maxsize=128, ttl=_CACHE_TTL)
_expression_cache = threading.local()


def _get_compiled_expression(expr: str) -> jsonata.Jsonata:
    cache = getattr(_expression_cache, "compiled", None)
    if cache is None:
        cache = {}
        _expression_cache.compiled = cache
    compiled = cache.get(expr)
    if compiled is None:
        compiled = jsonata.Jsonata(expr)
        cache[expr] = compiled
    return compiled


class BaseTranslatorConfig(BaseModel):
    source_schema: dict = Field(..., description="The JSON schema of the source data")
    target_schema: dict = Field(..., description="The JSON schema of the target data")
    mappings: List[str] = Field(..., description="List of transformation expressions")
    validate_intermediately: bool = Field(
        default=True, description="Validate against target schema after each mapping merge"
    )


class BaseTranslator:
    def __init__(self, config: BaseTranslatorConfig):
        self.config = config
        self.source_schema = config.source_schema
        self.target_schema = config.target_schema
        self.mappings = config.mappings

    def run(self, input: dict) -> dict:
        # #1157: this loop is the export hot path. A CLR/OB3 export evaluates ~32
        # expressions over the composed learner record and has run right at the
        # caller's timeout on demo. Stage timings are accumulated and emitted as one
        # summary line so the next slow run is diagnosable from logs alone, instead of
        # having to reproduce it. Cheap: perf_counter calls, no per-mapping logging.
        t_start = perf_counter()

        # validate input against source schema
        self._validate_against_schema(data=input, schema=self.source_schema)
        t_source_validated = perf_counter()

        # apply mapping expressions to transform input to target schema
        result: dict = {}
        eval_seconds = 0.0
        merge_seconds = 0.0
        applied = discarded = eval_errors = non_object = 0

        for mapping_expression_str in self.mappings:
            try:
                t0 = perf_counter()
                mapping_expression = _get_compiled_expression(mapping_expression_str)
                fragment = mapping_expression.evaluate(input)
                eval_seconds += perf_counter() - t0
                # DEBUG, not INFO: two lines per mapping per request, and `fragment`
                # can be large. The summary below carries the operational signal.
                logger.debug("Mapping: %s", mapping_expression_str)
                logger.debug("Fragment: %s", fragment)
            except Exception as e:
                eval_errors += 1
                logger.warning("Skipping mapping due to evaluation error: %s", e)
                continue

            # Only merge object-shaped fragments; ignore scalars/None
            if not isinstance(fragment, dict):
                non_object += 1
                logger.warning("Skipping non-object fragment: %r", fragment)
                continue

            # Tentative merge -> validate -> commit or rollback
            t1 = perf_counter()
            if self.config.validate_intermediately:
                tentative = deepcopy(result)
                deep_merge(tentative, fragment)

                try:
                    # If you want to be strict about *partial* validity, validate after each merge:
                    self._validate_against_schema(data=tentative, schema=self.target_schema)
                    result = tentative
                    applied += 1
                except ValueError as e:
                    discarded += 1
                    logger.warning("Discarding fragment due to target schema violation: %s", e)
                    # do not apply this fragment
                finally:
                    merge_seconds += perf_counter() - t1
            else:
                # Skip intermediate validation and the rollback copy it requires;
                # the final validation below is the sole gate.
                deep_merge(result, fragment)
                applied += 1
                merge_seconds += perf_counter() - t1

        # final validation (should already be valid if the per-fragment check is kept)
        self._validate_against_schema(data=result, schema=self.target_schema)

        total = perf_counter() - t_start
        logger.info(
            "Translation complete in %.2fs (source-validate %.2fs, jsonata-eval %.2fs, merge+validate %.2fs); "
            "mappings=%d applied=%d discarded=%d eval_errors=%d non_object=%d",
            total,
            t_source_validated - t_start,
            eval_seconds,
            merge_seconds,
            len(self.mappings),
            applied,
            discarded,
            eval_errors,
            non_object,
        )
        logger.debug("Translation result: %s", result)
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

    async def run(self, input: dict, tenant_schema: str | None = None) -> dict:
        source_schema = await self._fetch_schema(self.source_schema_id, tenant_schema=tenant_schema)
        target_schema = await self._fetch_schema(self.target_schema_id, tenant_schema=tenant_schema)

        transformation = await self._fetch_transformation(
            self.source_schema_id, self.target_schema_id, tenant_schema=tenant_schema
        )
        logger.info("Transformation: %s", transformation)
        mappings = convert_transformation_to_mappings(transformation)

        base_translator_config = BaseTranslatorConfig(
            source_schema=source_schema, target_schema=target_schema, mappings=mappings
        )
        base_translator = BaseTranslator(config=base_translator_config)
        result = base_translator.run(input)

        return result

    async def _fetch_schema(self, schema_id: str, tenant_schema: str | None = None) -> dict:
        cache_key = f"{schema_id}:{tenant_schema or ''}"
        cached = _schema_cache.get(cache_key)
        if cached is not None:
            logger.info("Cache hit for schema %s", schema_id)
            return cached
        result = await get_data_model_schema(
            schema_id, include_attr_md=True, include_entity_md=False, tenant_schema=tenant_schema
        )
        _schema_cache[cache_key] = result
        return result

    async def _fetch_transformation(
        self, source_schema_id: str, target_schema_id: str, tenant_schema: str | None = None
    ) -> dict:
        cache_key = f"{source_schema_id}:{target_schema_id}:{tenant_schema or ''}"
        cached = _transformation_cache.get(cache_key)
        if cached is not None:
            logger.info("Cache hit for transformation %s -> %s", source_schema_id, target_schema_id)
            return cached
        result = await get_data_model_transformation(source_schema_id, target_schema_id, tenant_schema=tenant_schema)
        _transformation_cache[cache_key] = result
        return result
