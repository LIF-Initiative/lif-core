# `lif_to_lif_adapter` — Adapter

Reads from another LIF GraphQL API. Used when one LIF deployment needs to pull learner data from a peer LIF deployment — typically in multi-org demos where org1's orchestrator fetches data hosted by org2 or org3.

## Files

| File | What it does |
|---|---|
| `adapter.py` | `LIFToLIFAdapter` — implements the `LIFDataSourceAdapter` contract |
| `graphql_query_all_fields_org2.graphql` | Pre-baked query template for org2 |
| `graphql_query_all_fields_org3.graphql` | Pre-baked query template for org3 |

The per-org `.graphql` files exist because schema field selection is hard to template dynamically against an evolving LIF data model; keeping the queries as text files makes them easy to inspect and edit. Generic adapters that target arbitrary LIF deployments will need to generate selections at runtime — that work isn't done here.

## Registered as
`lif-to-lif` (see [`../README.md`](../README.md) for the registry).
