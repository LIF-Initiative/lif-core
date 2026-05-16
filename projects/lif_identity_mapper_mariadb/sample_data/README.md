# `sample_data/` — Identity Mapper seed datasets

Per-organization seed data for the Identity Mapper MariaDB instance. Each subdirectory holds the mappings needed for one demo org partition; the `SEED_DATA_KEY` env var on the container selects which one to load.

## Subdirectories

| Partition | Purpose |
|---|---|
| `advisor-demo-org1/` | Matt, Renee, Sarah, Tracy — org1's native users |
| `advisor-demo-org2/` | Alan, Jenna, Sarah, Tracy — org2's native users |
| `advisor-demo-org3/` | Alan, Jenna, Matt, Renee — org3's native users |

The cross-org duplication (e.g., Sarah in both org1 and org2) is intentional — it exercises the identity-mapping layer when the same person needs to be resolved across orgs with different identifier conventions.

For the broader test-user matrix (including async ingestion flows), see CLAUDE.md § "Integration Tests."
