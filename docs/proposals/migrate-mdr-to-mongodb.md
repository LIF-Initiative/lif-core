# Option C: Migrate MDR from PostgreSQL to MongoDB

**Date:** 2026-02-19
**Status:** Draft — discussion only

---

## Summary

Replace the MDR's PostgreSQL relational database with MongoDB. The MDR stores metadata about data standards (schemas, entities, attributes, value sets, transformations, mappings) — a domain that is arguably a better fit for a document model than rigid relational tables. The current relational schema has 15 tables, 20+ foreign key constraints, 8 custom PostgreSQL enum types, a stored procedure, and Flyway migrations.

This option can be combined with Option A (generalize types) or Option B (simplify to flat schemas). It addresses the storage layer independently of the type system question.

---

## Why Consider This Change

**Arguments for MongoDB:**
- The MDR models hierarchical, schema-like data (entities containing attributes, value sets containing values, transformation groups containing transformations). Documents naturally represent these nested structures without join tables.
- The project already runs MongoDB for learner data storage. Consolidating on one database technology reduces operational complexity and team cognitive load.
- Schema evolution is simpler — adding fields to a document doesn't require migrations, ALTER TABLE, or enum updates.
- The current `ExtInclusionsFromBaseDM` join table, `EntityAssociation`, `EntityAttributeAssociation`, and similar relationship tables could collapse into embedded arrays within parent documents.
- Value set mappings and transformations are inherently document-shaped (nested, variable structure, JSONata expressions).

**Arguments for keeping PostgreSQL:**
- The MDR has well-defined, stable relationships that relational databases model cleanly.
- Foreign key constraints enforce data integrity at the database level — MongoDB relies on application-level enforcement.
- Existing Flyway migrations, stored procedures, and AWS RDS Aurora infrastructure are already built and working.
- Transactional consistency across multiple tables is simpler in PostgreSQL.
- The team has already invested in the SQLModel/SQLAlchemy async stack.

---

## Current Relational Schema

### Tables (15)

| Table | Purpose | Key Relationships |
|-------|---------|-------------------|
| `DataModels` | Schema definitions | Self-ref via `BaseDataModelId` |
| `Entities` | Entities within a schema | FK → DataModels |
| `Attributes` | Entity attributes | FK → DataModels, FK → ValueSets |
| `EntityAssociation` | Parent-child entity relationships | FK → Entities (parent & child) |
| `EntityAttributeAssociation` | Entity-attribute join | FK → Entities, FK → Attributes |
| `Constraints` | Attribute constraints | FK → Attributes (CASCADE) |
| `DataModelConstraints` | Schema-level constraints | FK → DataModels |
| `ValueSet` | Enumerated value sets | FK → DataModels |
| `ValueSetValue` | Individual values | FK → ValueSets, FK → DataModels |
| `ValueSetValueMapping` | Source→target value mappings | FK → ValueSetValues, FK → TransformationsGroup |
| `TransformationGroup` | Grouped transformations | FK → DataModels (source & target) |
| `Transformation` | Transformation rules | FK → TransformationsGroup |
| `TransformationAttribute` | Transformation I/O attributes | FK → Entities, Attributes, Transformations |
| `ExtInclusionsFromBaseDM` | Extension inclusion tracking | FK → DataModels |
| `ExtMappedValueSet` | Extension value set mapping | FK → ValueSets |

### SQL-Specific Features in Use
- 8 custom PostgreSQL ENUM types (accesstype, datamodeltype, constrainttype, etc.)
- Stored procedure: `deletedatamodelrecords()` for cascade cleanup
- PostgreSQL extensions: `pg_stat_statements`, `pgaudit`
- 20+ foreign key constraints with ON DELETE CASCADE
- GENERATED ALWAYS AS IDENTITY sequences
- Server-side timestamp defaults with timezone
- AWS RDS Aurora PostgreSQL with IAM authentication

---

## Proposed MongoDB Document Model

### Collection: `schemas`

Replaces: `DataModels`, and optionally absorbs `Entities`, `Attributes`, `EntityAssociation`, `EntityAttributeAssociation`, `Constraints`, `DataModelConstraints`

```json
{
  "_id": "ObjectId",
  "name": "LIF",
  "description": "Learner Information Framework",
  "version": "1.0",
  "state": "Published",
  "organization": "LIF Initiative",
  "tags": ["learner", "interoperability"],
  "created_at": "ISODate",
  "entities": [
    {
      "entity_id": "uuid",
      "name": "Person",
      "description": "A learner or individual",
      "attributes": [
        {
          "attribute_id": "uuid",
          "name": "firstName",
          "data_type": "string",
          "required": true,
          "constraints": [
            { "type": "Length", "max": 255 }
          ]
        }
      ],
      "children": [
        {
          "child_entity_id": "uuid",
          "name": "Name",
          "placement": "Embedded",
          "cardinality": "one-to-many"
        }
      ]
    }
  ]
}
```

### Collection: `value_sets`

Replaces: `ValueSet`, `ValueSetValue`

```json
{
  "_id": "ObjectId",
  "name": "IdentifierType",
  "schema_id": "ObjectId (ref to schemas)",
  "values": [
    { "value_id": "uuid", "code": "SSN", "description": "Social Security Number" },
    { "value_id": "uuid", "code": "SCHOOL_ASSIGNED_NUMBER", "description": "..." }
  ]
}
```

### Collection: `transformations`

Replaces: `TransformationGroup`, `Transformation`, `TransformationAttribute`, `ValueSetValueMapping`

```json
{
  "_id": "ObjectId",
  "name": "SIS to LIF",
  "source_schema_id": "ObjectId",
  "target_schema_id": "ObjectId",
  "state": "Published",
  "rules": [
    {
      "rule_id": "uuid",
      "source_path": "student.first_name",
      "target_path": "Person.Name.firstName",
      "expression_language": "JSONata",
      "expression": "$source.first_name",
      "value_set_mappings": [
        {
          "source_value": "SSN",
          "source_value_set": "id_types",
          "target_value": "SSN",
          "target_value_set": "IdentifierType"
        }
      ]
    }
  ]
}
```

### Collection: `extension_mappings` (only if keeping inheritance — Option A)

Replaces: `ExtInclusionsFromBaseDM`, `ExtMappedValueSet`

If Option B (flat model) is chosen, this collection is not needed.

---

## Work Breakdown

### 1. MongoDB Infrastructure
- Add MongoDB instance for MDR to Docker Compose (or reuse existing MongoDB)
- Replace AWS RDS Aurora PostgreSQL with DocumentDB or MongoDB Atlas in CloudFormation
- Remove Flyway migration infrastructure for MDR
- **Estimate: 4–6 hours**

### 2. Data Model Layer — Replace SQLModel with Motor/Beanie/PyMongo
- Remove `mdr_sql_model.py` (SQLModel definitions, enums)
- Create MongoDB document models (Beanie ODM or raw Motor)
- Replace `database_setup.py` async PostgreSQL session with Motor async client
- Remove `sql_util.py` raw SQL utilities
- **Estimate: 8–10 hours**

### 3. Service Layer — Rewrite Queries
- Rewrite all services (`datamodel_service.py`, `entity_service.py`, `attribute_service.py`, `valueset_service.py`, `transformation_service.py`, `constraint_service.py`, `inclusions_service.py`)
- Replace SQLModel `select()` / `where()` with MongoDB queries
- Replace join-based queries with document lookups and `$lookup` aggregations where needed
- Replace stored procedure with application-level cascade logic
- Adapt soft-delete pattern (same concept, different query syntax)
- Adapt pagination (offset/limit works similarly)
- **Estimate: 20–28 hours**

### 4. API Endpoints — Minimal Changes
- Endpoints mostly delegate to services, so changes are minor
- Update any response models that exposed SQLModel-specific fields
- Remove or adapt ID handling (auto-increment integers → ObjectIds or UUIDs)
- **Estimate: 4–6 hours**

### 5. Jinja Template Service
- Rewrite `jinja_helper_service.py` queries for MongoDB
- Schema export and OpenAPI generation logic needs MongoDB data access
- **Estimate: 4–6 hours**

### 6. Data Migration
- Write migration script: PostgreSQL → MongoDB document transformation
- Map relational joins to embedded documents
- Preserve IDs for backward compatibility or define new ID scheme
- Test migration with existing dev/demo data
- **Estimate: 6–8 hours**

### 7. Frontend — ID and Response Format Changes
- Update API response handling if ID format changes (integer → string/ObjectId)
- Minimal other changes — frontend talks to REST API, not directly to DB
- **Estimate: 2–4 hours**

### 8. Testing
- Rewrite all MDR service unit tests for MongoDB
- Update integration tests
- Add MongoDB test fixtures (replace SQL seed data)
- **Estimate: 10–14 hours**

### 9. Remove PostgreSQL Infrastructure
- Remove Flyway files, stored procedures, SAM database templates
- Remove `asyncpg`, `psycopg2-binary`, `sqlmodel` dependencies from MDR project
- Remove `sql_util.py`, sync database connection code
- Clean up Docker Compose (remove PostgreSQL container, restore container)
- **Estimate: 3–4 hours**

### 10. Documentation
- Update CLAUDE.md, deployment guides, SAM README
- Document new MongoDB schema and connection setup
- **Estimate: 2–3 hours**

---

## Effort Summary

| Area | Estimated Hours |
|------|----------------|
| MongoDB infrastructure | 4–6 |
| Data model layer (ODM) | 8–10 |
| Service layer rewrite | 20–28 |
| API endpoints | 4–6 |
| Jinja template service | 4–6 |
| Data migration script | 6–8 |
| Frontend adjustments | 2–4 |
| Testing | 10–14 |
| Remove PostgreSQL infra | 3–4 |
| Documentation | 2–3 |
| **Total** | **63–89 hours** |

These estimates assume AI-assisted development. Without AI assistance, expect roughly 2–3x.

---

## Comparison: All Three Options

| | Option A: Generalize Types | Option B: Simplify (Flat) | Option C: MongoDB Migration |
|---|---|---|---|
| **Approach** | Rename types, keep inheritance | Remove types and inheritance | Replace database engine |
| **Estimate** | 44–66 hrs | 32–46 hrs | 63–89 hrs |
| **Can combine with** | Option C | Option C | Option A or B |
| **Complexity after** | Same structure, generic names | Significantly reduced | Different technology, simpler documents |
| **Operational impact** | Low — same DB, same infra | Low — same DB, less schema | High — new DB engine, new infra |
| **Team skill alignment** | Same stack | Same stack | Aligns with existing MongoDB usage elsewhere |
| **Schema evolution** | Still requires migrations | Still requires migrations | No migrations needed |
| **Data integrity** | FK constraints enforced by DB | FK constraints enforced by DB | Application-level enforcement |

### Recommended Combinations

- **Option B + C** (simplify types AND move to MongoDB): **78–113 hours combined** (some overlap reduces total). This is the most transformative option — flat schema model stored as documents. Eliminates both the type hierarchy complexity and the relational overhead.
- **Option A + C** (generalize types AND move to MongoDB): **88–127 hours combined**. Less value — you'd be migrating complexity to a new database rather than eliminating it.
- **Option B alone**: Best ROI if the relational database isn't causing pain beyond the type system.
- **Option C alone**: Best if the primary pain is the relational model and migration overhead, but the type system is acceptable.

---

## Risks & Considerations

- **Service layer rewrite is the largest cost**: 7 service files with complex query logic all need rewriting. This is where most bugs will be introduced.
- **Loss of referential integrity**: PostgreSQL enforces FK constraints at the DB level. MongoDB requires application-level enforcement or accepts eventual consistency. Bugs in cascade deletes or orphaned documents become possible.
- **AWS DocumentDB vs MongoDB Atlas**: DocumentDB has MongoDB API compatibility gaps (no multi-document transactions in older versions, limited aggregation pipeline support). MongoDB Atlas is fully compatible but adds a vendor dependency. Evaluate which is appropriate for the AWS deployment.
- **Identity Mapper**: The identity mapper service uses a separate MariaDB database. This proposal does not cover migrating that — it could be a follow-on effort.
- **Existing backup/restore**: The current Docker setup uses `pg_dump`/`pg_restore`. MongoDB uses `mongodump`/`mongorestore` — backup scripts need updating.
- **Audit and compliance**: `pgaudit` extension provides query-level audit logging. MongoDB has its own audit log capability but configuration differs.
