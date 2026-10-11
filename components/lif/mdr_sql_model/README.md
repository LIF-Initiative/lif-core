# `mdr_sql_model` — Component

SQLModel/SQLAlchemy ORM table definitions for MDR persistence. Split out of
[`datatypes`](../datatypes/) so that services which only need core LIF types
don't have to pull in MDR's SQLAlchemy/SQLModel dependency.

## Layout

| File | Contents |
|---|---|
| `core.py` | `DataModel`, `Entity`, `EntityAssociation`, `ValueSet`, `ValueSetValue`, `Attribute`, `EntityAttributeAssociation`, `Constraint`, `DataModelConstraints`, `TransformationGroup`, `Transformation`, `TransformationAttribute`, `ValueSetValueMapping`, `ExtInclusionsFromBaseDM`, `ExtMappedValueSet`, plus their supporting enums |

## Used by
- `mdr_dto` — DTO enums mirror the ORM enums defined here
- `mdr_services` — reads/writes these tables
- `bases/lif/mdr_restapi` — `datamodel_endpoints.py` references the enums directly

This component is MDR-internal, in the same sense as `mdr_dto`: other services
that need MDR data should call the MDR API via `mdr_client`, not import these
models directly.
