# Schema Loading & Data Model

How services load the LIF schema, the PascalCase/camelCase naming convention, and the GraphQL implementation details that depend on it. The normative rules live in [`docs/specs/data-model-rules.md`](../../specs/data-model-rules.md); this doc is the agent-oriented implementation reference.

## Schema Hierarchy
1. **`reference_data/schemas/lif-schema.json`** - Source of truth for LIF data model rules and policies
2. **MDR (Metadata Registry)** - Captures schema dynamically, allows extension by deployers
3. **Seed data** - Must validate against the schema from MDR
4. **Components** - Must honor the schema, load from MDR with short cache if needed
5. **GraphQL queries** - Should align with schema as best as practical

## Schema Loading Pattern (IMPORTANT)

Services load OpenAPI schema from MDR at startup. Key design decisions:

**No silent fallback to file:**
- If MDR is configured but unavailable, the service **fails with a clear error** (does not silently fall back to bundled file)
- This prevents using stale/outdated schema data in production
- Use `USE_OPENAPI_DATA_MODEL_FROM_FILE=true` to explicitly use bundled file (development only)

**Configuration via `LIFSchemaConfig`:**
- All schema-related config should use `LIFSchemaConfig.from_environment()` (not direct `os.getenv()`)
- Provides centralized validation and consistent defaults
- Key env vars: `OPENAPI_DATA_MODEL_ID`, `LIF_MDR_API_URL`, `USE_OPENAPI_DATA_MODEL_FROM_FILE`

**SchemaStateManager component** (`components/lif/schema_state_manager/`):
- Shared component for services that need schema data (semantic search, GraphQL)
- Handles sync and async initialization
- Thread-safe state access via lock
- Tracks schema source ("mdr" or "file")
- Supports schema refresh without restart

```python
from lif.schema_state_manager import SchemaStateManager
from lif.lif_schema_config import LIFSchemaConfig

config = LIFSchemaConfig.from_environment()
manager = SchemaStateManager(config)
manager.initialize_sync()  # or await manager.initialize()

state = manager.state  # Access schema leaves, filter models, embeddings
```

## Capitalization Convention (IMPORTANT)

The LIF schema uses a specific naming convention based on data type:

| Type | Case | Examples |
|------|------|----------|
| **Entity/Object/Array properties** | PascalCase | `Name`, `Contact`, `Identifier`, `EmploymentLearningExperience`, `CredentialAward`, `Proficiency` |
| **Scalar attributes** | camelCase | `firstName`, `lastName`, `identifier`, `identifierType`, `informationSourceId`, `startDate` |

**Example structure:**
```json
{
  "person": [{
    "Name": [{                           // PascalCase - array of objects
      "firstName": "John",               // camelCase - scalar attribute
      "lastName": "Doe",
      "informationSourceId": "Org1"
    }],
    "Identifier": [{                     // PascalCase - array of objects
      "identifier": "12345",             // camelCase - scalar attribute
      "identifierType": "SCHOOL_ASSIGNED_NUMBER"
    }],
    "EmploymentPreferences": [{          // PascalCase - array of objects
      "organizationTypes": ["Public"]    // camelCase - scalar attribute
    }]
  }]
}
```

### Files That Must Follow This Convention
- **Seed data**: `projects/mongodb/sample_data/**/*.json`
- **GraphQL queries**: `components/lif/data_source_adapters/**/*.graphql`
- **Config files**: `deployments/**/information_sources_config*.yml` (fragment paths like `person.Name`)
- **Test fixtures**: Any test data in `test/`

## Key Implementation Details

1. **Strawberry GraphQL types** (`type_factory.py`):
   - Uses `strawberry.field(name=field_name)` to preserve original schema case
   - `resolve_actual_type()` preserves `List` wrappers for proper type resolution
   - `dict_to_dataclass()` handles nested type conversion
   - **Resolver annotations must use `Info` type** — dynamic resolvers in `build_root_query_type` and `build_root_mutation_type` must annotate `info` as `strawberry.types.Info`, not `object` or `Any`. Strawberry identifies the `info` parameter by type (name-based fallback was removed in 0.297.0).
   - **MDR schemas have no `$ref`** — the MDR `generate_openapi_schema()` function deep-copies and inlines all referenced schemas. The `$ref` branch in `create_type()` exists but is not exercised by production schemas.

2. **Fragment paths** use format `person.EntityName` (e.g., `person.EmploymentPreferences`)

3. **Translator service** returns data with PascalCase root (`Person` not `person`)
   - The `adjust_lif_fragments_for_initial_orchestrator_simplification()` function uses case-insensitive key lookup to handle this

4. **Filter inputs** in GraphQL also use PascalCase for entity names:
   ```graphql
   person(filter: { Identifier: { identifier: "12345", identifierType: "..." } })
   ```
