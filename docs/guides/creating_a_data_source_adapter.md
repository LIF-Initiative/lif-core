# Creating a Data Source Adapter

This guide covers how to build a custom data source adapter to bring external data into the LIF system. It is aimed at developers who want to write a new adapter from scratch or adapt the reference implementation to their own data source.

> **See also:** [LIF_Add_Data_Source.md](LIF_Add_Data_Source.md) for a walkthrough that also covers MDR schema setup and Docker Compose configuration.

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

### Step 4: Configure credentials

Set environment variables on the `dagster-code-location` container. The naming convention is:

```
ADAPTERS__<ADAPTER_ID>__<INFORMATION_SOURCE_ID>__CREDENTIALS__<KEY>
```

Dashes in the adapter ID and source ID are converted to underscores, and everything is uppercased. For example, if your `adapter_id` is `my-source-to-lif` and the information source ID is `org1-acme-sis`:

```bash
ADAPTERS__MY_SOURCE_TO_LIF__ORG1_ACME_SIS__CREDENTIALS__HOST=api.example.com
ADAPTERS__MY_SOURCE_TO_LIF__ORG1_ACME_SIS__CREDENTIALS__SCHEME=https
ADAPTERS__MY_SOURCE_TO_LIF__ORG1_ACME_SIS__CREDENTIALS__TOKEN=your-secret-token
```

Missing credentials produce a warning at startup but do not block initialization. Your adapter's `__init__` should handle missing values gracefully (e.g., default `scheme` to `"https"`).

### Step 5: Add the information source to config

Add an entry to the query planner's information sources config (e.g., `information_sources_config_org1.yml`):

```yaml
information_sources:
  # ... existing sources ...
  - information_source_id: "org1-acme-sis"
    information_source_organization: "Org1"
    adapter_id: "my-source-to-lif"
    ttl_hours: 24
    lif_fragment_paths:
      - "Person.Contact"
      - "Person.EmploymentPreferences"
    translation:
      source_schema_id: "28"     # MDR ID of your source schema
      target_schema_id: "17"     # MDR ID of the Org LIF schema
```

Key config fields:

| Field | Description |
|-------|-------------|
| `information_source_id` | Unique name for this data source instance |
| `adapter_id` | Must match your adapter's `adapter_id` class variable |
| `lif_fragment_paths` | LIF schema paths this source provides (2 levels deep: `Person.EntityName`) |
| `translation` | Required for pipeline-integrated adapters. IDs reference MDR data models. |
| `ttl_hours` | How long results are cached before re-fetching |

### Step 6: Set up translation in the MDR

For pipeline-integrated adapters, the MDR must have:

1. **A source schema** — describes the structure of your API's response. Each field uses a dot-path as its unique name (e.g., `user.details.address.city`). Only attributes (leaf fields) can be mapped.

2. **Transformation mappings** — JSONata expressions that map source fields to target LIF schema fields. These are created in the MDR Mappings tab by drawing connections between source and target attributes.

The `source_schema_id` and `target_schema_id` in your config must match the MDR data model IDs. The target is typically `17` (the Org LIF schema) in the reference implementation.

> **Note:** There is a known MDR issue where JSONata expressions may need manual lowercasing. After creating a mapping, double-click the mapping line and ensure the entity names in the expression are lowercase (e.g., `person`, `contact`, not `Person`, `Contact`).

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

### Check Dagster run logs

Navigate to `http://localhost:3000/runs/` and inspect the sub-process for your adapter. The logs will show your `logger.info` and `logger.error` messages.

### Empty fragment paths

If a translation yields an empty LIF fragment, the Dagster job will fail when saving results to the Query Planner. Verify that your MDR JSONata expressions produce the expected output and that entity names are lowercased in the expressions.

### Cache interference

The Query Cache service caches results for `ttl_hours`. During development, you may need to clear the cache. Stop services, delete the `mongodb-org1` Docker volume, and restart.

### Credential issues

If your adapter receives empty credentials, check:
- The env var naming matches the convention exactly (uppercased, dashes to underscores)
- The env vars are set on the `dagster-code-location` container (not another service)
- Your adapter's `credential_keys` list includes all the keys you need
