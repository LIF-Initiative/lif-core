# Creating a Data Source Adapter

This guide is the **reference** for the data source adapter contract: what adapters are, what they receive, what they return, and how to write one. It is aimed at developers adapting their own code to the LIF system or writing a new adapter from scratch.

> **Looking for an end-to-end walkthrough?** [`add-data-source.md`](add-data-source.md) is the tutorial. It walks through a concrete scenario — building an SIS-style adapter, setting up the MDR source schema and JSONata mappings, wiring up Docker Compose, and verifying via GraphQL. Use that guide when you want step-by-step instructions; use this one when you need to understand the adapter contract.

## How Adapters Fit In

The **Orchestrator** (Dagster) executes adapters to fetch person data from external sources. Each adapter is a Python class that knows how to talk to one kind of data source. The orchestrator calls adapters based on a **query plan** — a list of instructions that says "for this person, fetch these fields from this source using this adapter."

```
Query Planner                    Orchestrator (Dagster)
    │                                │
    │  query plan parts              │
    └───────────────────────────────>│
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                 │
                Adapter A        Adapter B         Adapter C
                (LIF-to-LIF)    (REST API)        (Your adapter)
                    │                │                 │
                    │                │    ┌────────────┘
                    │                │    │
                    │           Translator Service
                    │                │    │
                    └────────┬───────┘────┘
                             │
                      Query Planner
                      (stores results)
```

There are two flows:

1. **LIF-to-LIF** — The source already returns data in LIF schema format. The adapter returns structured `OrchestratorJobQueryPlanPartResults` directly. No translation needed.

2. **Pipeline-integrated** — The source returns data in its own format. The adapter returns raw JSON (`dict`). The orchestrator then sends this to the **Translator** service, which uses MDR-defined transformation rules to convert it into LIF schema format.

Most custom adapters will use the pipeline-integrated flow.

## What the Adapter Receives

When the orchestrator instantiates your adapter, it passes two arguments:

### `lif_query_plan_part: LIFQueryPlanPart`

Contains everything the adapter needs to know about what data to fetch:

| Field | Type | Description |
|-------|------|-------------|
| `person_id` | `LIFPersonIdentifier` | The person to look up. Has `.identifier` (e.g., `"100001"`) and `.identifierType` (e.g., `"School-assigned number"`) |
| `information_source_id` | `str` | Which configured data source this is (e.g., `"org1-acme-sis"`) |
| `adapter_id` | `str` | Your adapter's registered ID (e.g., `"acme-sis-to-lif"`) |
| `lif_fragment_paths` | `List[str]` | Which LIF data fields are needed (e.g., `["Person.Contact", "Person.Name"]`) |
| `translation` | `LIFQueryPlanPartTranslation \| None` | If set, has `source_schema_id` and `target_schema_id` for the translator |

### `credentials: dict`

Key-value pairs loaded from environment variables. The keys come from your adapter's `credential_keys` class variable. Common keys: `host`, `scheme`, `token`.

## What the Adapter Returns

### Pipeline-integrated adapters (most custom adapters)

Return the raw JSON response from your data source as a Python `dict`. The orchestrator passes this to the Translator service, which applies MDR-defined JSONata transformation rules to map it into LIF schema format.

```python
def run(self) -> dict:
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()
```

The translator will:
1. Fetch the source and target schemas from the MDR (using the IDs in `translation`)
2. Fetch the JSONata transformation expressions from the MDR
3. Apply the transformations to convert your source data into LIF-formatted fragments
4. Return `OrchestratorJobQueryPlanPartResults` with the translated data

This means your adapter does not need to know anything about the LIF schema. It just fetches data from the source in whatever format the source provides. The schema mapping is handled entirely in the MDR configuration.

### LIF-to-LIF adapters

If your source already returns LIF-formatted data, return `OrchestratorJobQueryPlanPartResults` directly:

```python
def run(self) -> OrchestratorJobQueryPlanPartResults:
    # ... fetch data ...
    return OrchestratorJobQueryPlanPartResults(
        information_source_id=self.lif_query_plan_part.information_source_id,
        adapter_id=self.lif_query_plan_part.adapter_id,
        data_timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
        person_id=self.lif_query_plan_part.person_id,
        fragments=[LIFFragment(fragment_path="person.all", fragment=[data])],
        error=None,
    )
```

## Writing Your Adapter

### Step 1: Create the adapter directory

```
components/lif/data_source_adapters/
└── my_source_adapter/
    ├── __init__.py
    └── adapter.py
```

### Step 2: Implement the adapter class

Your adapter must subclass `LIFDataSourceAdapter` and define three class variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `adapter_id` | Yes | Unique string ID (e.g., `"my-source-to-lif"`). Used in config files and env vars. |
| `adapter_type` | Yes | One of: `LIFAdapterType.PIPELINE_INTEGRATED`, `LIF_TO_LIF`, `STANDALONE`, `AI_WRITE` |
| `credential_keys` | No | List of credential keys your adapter needs (defaults to `[]`) |

You must also implement `__init__` (accepting `lif_query_plan_part` and `credentials`) and `run()`.

Here is a complete example for a REST API data source:

```python
# components/lif/data_source_adapters/my_source_adapter/adapter.py

import requests

from lif.datatypes import LIFQueryPlanPart
from lif.logging import get_logger
from ..core import LIFAdapterType, LIFDataSourceAdapter

logger = get_logger(__name__)


class MySourceAdapter(LIFDataSourceAdapter):
    adapter_id = "my-source-to-lif"
    adapter_type = LIFAdapterType.PIPELINE_INTEGRATED
    credential_keys = ["host", "scheme", "token"]

    def __init__(self, lif_query_plan_part: LIFQueryPlanPart, credentials: dict):
        self.lif_query_plan_part = lif_query_plan_part
        self.host = credentials.get("host")
        self.scheme = credentials.get("scheme") or "https"
        self.token = credentials.get("token")

    def run(self) -> dict:
        identifier = self.lif_query_plan_part.person_id.identifier or ""
        url = f"{self.scheme}://{self.host}/api/people/{identifier}"

        headers = {"Authorization": f"Bearer {self.token}"}

        logger.info(f"Fetching from {url}")

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()

        if "errors" in result:
            error_msg = f"Source API errors: {result['errors']}"
            logger.error(error_msg)
            raise Exception(error_msg)

        logger.info("Source query executed successfully")
        return result
```

And the `__init__.py`:

```python
# components/lif/data_source_adapters/my_source_adapter/__init__.py

from .adapter import MySourceAdapter

__all__ = ["MySourceAdapter"]
```

### Step 3: Register the adapter

Add your adapter to the registry in `components/lif/data_source_adapters/__init__.py`:

```python
from .my_source_adapter import MySourceAdapter

_EXTERNAL_ADAPTERS = {
    "example-data-source-rest-api-to-lif": ExampleDataSourceRestAPIToLIFAdapter,
    "my-source-to-lif": MySourceAdapter,  # <-- add this
}
```

The registry key must match your adapter's `adapter_id`.

### Step 4: Wire it up

Once the adapter class is written and registered, three more things need to happen before it runs:

1. **Credentials** — set environment variables on the `dagster-code-location` container using the naming convention `ADAPTERS__<ADAPTER_ID>__<INFORMATION_SOURCE_ID>__CREDENTIALS__<KEY>` (uppercased, dashes converted to underscores). Missing credentials produce a warning at startup but do not block initialization, so handle absent values gracefully in `__init__`.

2. **Information source config** — add an entry to the query planner's `information_sources_config_*.yml` referencing your `adapter_id`, the `lif_fragment_paths` your source provides, and a `translation` block with the MDR schema IDs (for pipeline-integrated adapters).

3. **MDR schemas and mappings** — create a source schema describing your API response and JSONata mappings to the target LIF schema. Only attributes (leaf fields) can be mapped.

[`add-data-source.md`](add-data-source.md) walks through each of these with a concrete example — use it as the step-by-step companion when you are ready to wire your adapter into a running environment.

## Adapter Design Guidelines

### Error handling

- **Raise exceptions on failure.** The orchestrator has built-in retry logic (3 retries with exponential backoff and jitter). Let exceptions propagate so retries can kick in.
- **Check for error payloads.** Many APIs return 200 with an `errors` field in the body. Check for this and raise if present.
- **Use timeouts.** Always set a timeout on HTTP requests (30 seconds is a reasonable default).

### Logging

Use the LIF logger:

```python
from lif.logging import get_logger
logger = get_logger(__name__)
```

Log at `info` level for key milestones (request URL, success) and `debug` for response payloads. The orchestrator logs are visible in Dagster's run view.

### Statelessness

Adapters are instantiated fresh for each query plan part execution. Do not store state between calls. Caching is handled upstream by the LIF Query Cache service.

### Network access

The adapter runs inside the `dagster-code-location` container. If your data source is on the host machine's localhost, use `host.docker.internal` as the hostname.

### Credential validation

You can override `validate_credentials` for custom checks:

```python
@classmethod
def validate_credentials(cls, credentials: dict) -> None:
    super().validate_credentials(credentials)
    if not credentials.get("token"):
        raise ValueError("Token is required for MySource adapter")
```

## Reference Implementations

The repository includes two adapters you can study or clone as a starting point:

| Adapter | Type | Returns | Path |
|---------|------|---------|------|
| `lif-to-lif` | `LIF_TO_LIF` | `OrchestratorJobQueryPlanPartResults` | `components/lif/data_source_adapters/lif_to_lif_adapter/` |
| `example-data-source-rest-api-to-lif` | `PIPELINE_INTEGRATED` | `dict` | `components/lif/data_source_adapters/example_data_source_rest_api_to_lif_adapter/` |

The `example-data-source-rest-api-to-lif` adapter is the simplest starting point for most custom adapters. It demonstrates the full pipeline-integrated flow in under 45 lines of code.

## Troubleshooting

For MDR mapping issues, empty fragments, cache invalidation, and Dagster run inspection, see the troubleshooting section of [`add-data-source.md`](add-data-source.md#troubleshooting). The items below are specific to adapter development.

### Adapter not found

If the orchestrator raises `Unknown adapter_id`, the adapter class is not in `ADAPTER_REGISTRY`. Verify the import and `_EXTERNAL_ADAPTERS` entry in `components/lif/data_source_adapters/__init__.py`, and that the registry key matches the `adapter_id` class variable exactly.

### Empty credentials

If your adapter receives an empty `credentials` dict, check:
- The env var naming matches the convention exactly (uppercased, dashes to underscores in both the adapter ID and information source ID)
- The env vars are set on the `dagster-code-location` container, not another service
- Your adapter's `credential_keys` list includes every key you read in `__init__` — only declared keys are loaded from the environment

### Exceptions that don't retry

The orchestrator retries adapter failures up to 3 times with exponential backoff — but only if your `run()` method raises. If you catch exceptions and return a malformed result instead, the orchestrator has nothing to retry on. Let exceptions propagate.
