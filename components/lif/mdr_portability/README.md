# `mdr_portability` — Component

The MDR portable file format: Pydantic models for the three file kinds, the named error codes, reading
a file with those codes, and writing it in canonical form, as specified in
[`docs/specs/mdr-portable-file-format.md`](../../../docs/specs/mdr-portable-file-format.md) (#1333).

## Public surface

```python
from lif.mdr_portability import (
    ModelFile, MappingGroupFile, CrosswalkFile,
    parse_model_file, parse_mapping_group_file, parse_crosswalk_file,
    check_model_file,
    dump_canonical,
    PortabilityError, PortabilityErrorGroup, PortabilityErrorCode,
)
```

| Name | What it is |
|---|---|
| `ModelFile` | One self-contained data model (Portability Spec §5) |
| `MappingGroupFile` | One transformation group, JSONata rules only (Portability Spec §6) |
| `CrosswalkFile` | Value mappings from one value set to another (Portability Spec §7) |
| `parse_model_file(content)`, `parse_mapping_group_file(content)`, `parse_crosswalk_file(content)` | Read a file from its bytes, which must be UTF-8. Checks the envelope first, then the file's shape, and raises every refusal at once as a `PortabilityErrorGroup` |
| `check_model_file(file)` | Check the rules of a model file that span elements, such as duplicate keys, and raise every refusal at once as a `PortabilityErrorGroup` |
| `dump_canonical(file)` | The file as canonical UTF-8 bytes, with lists sorted (Portability Spec §9) |
| `PortabilityError` | One refusal: `code`, `element` (by key or path, e.g. `Entities[Student].Id`) and `reason` |
| `PortabilityErrorGroup` | An `ExceptionGroup` of the `PortabilityError`s found in one file |
| `PortabilityErrorCode` | Every refusal the spec names (Portability Spec §10) |

Parsing checks each object's shape: required fields, types, and unknown keys. Rules that span
elements (duplicate keys, unresolved references, cycles, paths) are checked separately, by
`check_model_file` for a model file.

## Layout and format versions

| Module | Holds |
|---|---|
| `v1/models.py` | Format version 1's models |
| `v1/reading.py` | What reading a version 1 file needs: one `Reader` per file kind (deprecated keys, where identities are, how list items are named) |
| `reader.py` | The `Reader` type |
| `model_rules.py` | The current version's model rules that span elements |
| `parse.py` | The parsing steps, which are the same for every version, and `_READERS`: (`Format.Type`, `Format.Version`) → `Reader` |
| `canonical.py` | Writing the current version |
| `errors.py` | Codes and errors, for every version |

The package exports the current version's models under version-free names (`ModelFile`, not
`v1.models.ModelFile`), so callers never name a version. A version 2 would add a `v2/` package
(importing what it keeps from `v1`), a row per file kind in `_READERS`, and a step upgrading a
version 1 model to version 2, so that `parse_*` always return the current version (spec §4.2).

## Used by
- Nothing yet. The converter (Portability Spec §8) is the intended first consumer.
