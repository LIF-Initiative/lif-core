# `logging` — Component

The standard logger factory used across (almost) all LIF services. One module, one function, opinionated defaults: ISO timestamp with milliseconds, level name, logger name, message.

## Public surface

```python
from lif.logging import get_logger

logger = get_logger(__name__)
```

`LOG_LEVEL` env var (default `INFO`) controls verbosity. Format:

```
2025-10-09 14:33:21.123 INFO | my.logger | message
```

## When to use this vs. `mdr_utils/logger_config`

This component is the convention for non-MDR services. The MDR internals (`mdr_utils/logger_config.py`) use a slightly different format kept for historical compatibility — but new MDR endpoint code can use either since they share Python's `logging` module under the hood. New bases outside MDR should pull from here.

See [`docs/operations/guides/adding-a-new-microservice.md`](../../../docs/operations/guides/adding-a-new-microservice.md) for the full guidance.

## Used by
Most bases (api_graphql, advisor_restapi, query_cache_restapi, example_data_source_rest_api, semantic_search_mcp_server, orchestrator_restapi, translator_restapi, identity_mapper_restapi, query_planner_restapi) and many components.
