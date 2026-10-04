# `mdr_dto` — Component

Pydantic request/response models (DTOs) for the MDR API. One file per endpoint group; each defines the wire format for that group's create/update/list/get endpoints.

## Layout

| File | Endpoint group |
|---|---|
| `attribute_dto.py` | `/attributes` |
| `datamodel_dto.py` | `/datamodels` |
| `datamodel_constraints_dto.py` | `/datamodel_constraints` |
| `entity_dto.py` | `/entities` |
| `entity_association_dto.py` | `/entity_associations` |
| `entity_attribute_association_dto.py` | `/entity_attribute_associations` |
| `inclusion_dto.py` | `/inclusions` |
| `import_export_dto.py` | `/import_export` |
| `mdr_consumer_dto.py` | `MdrRetrieveDataModelsDTO` (used by `learner_data_export_api`, not an MDR endpoint itself) |
| `transformation_dto.py`, `transformation_group_dto.py` | `/transformation_groups` |
| `value_mapping_dto.py` | `/value_mappings` |
| `valueset_dto.py`, `value_set_values_dto.py` | `/value_sets`, `/value_set_values` |

Models follow the Pydantic v2 conventions used elsewhere (`from_attributes=True` instead of legacy `from_orm`; `model_dump` instead of `dict`).

## Used by
- `bases/lif/mdr_restapi` — every endpoint module imports its matching DTOs from here
- `bases/lif/learner_data_export_api` — imports `mdr_consumer_dto.MdrRetrieveDataModelsDTO` directly, since it's shaping a response it received *from* calling MDR, not defining an MDR endpoint of its own

This component is otherwise MDR-internal. Services that need MDR data should call the MDR API via `mdr_client`, not import these DTOs directly — the DTOs are wire shapes, not stable inter-service contracts.
