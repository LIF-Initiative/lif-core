# `mdr_portability` — Component

The MDR portable file format: Pydantic models for the three file kinds and the named error codes,
as specified in [`docs/specs/mdr-portable-file-format.md`](../../../docs/specs/mdr-portable-file-format.md) (#1333).

## Public surface

```python
from lif.mdr_portability import ModelFile, MappingGroupFile, CrosswalkFile, PortabilityErrorCode
```

| Name | What it is |
|---|---|
| `ModelFile` | One self-contained data model (Portability Spec §5) |
| `MappingGroupFile` | One transformation group, JSONata rules only (Portability Spec §6) |
| `CrosswalkFile` | Value mappings from one value set to another (Portability Spec §7) |
| `PortabilityErrorCode` | Every refusal the spec names (Portability Spec §10) |

The models check each object's shape: required fields, types, and unknown keys (`extra="forbid"`).
Rules that span elements (duplicate keys, unresolved references, cycles, paths) are the converter's.

## Used by
- Nothing yet. The converter (Portability Spec §8) is the intended first consumer.
