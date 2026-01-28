import dataclasses
import datetime as _dt
import enum
import re
from typing import Any, Dict, List, Optional, Union

import strawberry



# TODO: Replace with lif.string_utils function
def to_pascal_case_from_str(s: str) -> str:
    """Convert a string to PascalCase."""
    parts = re.findall(
        r"[A-Za-z][a-z]*|[A-Z]+(?![a-z])", s.replace("-", " ").replace("_", " ")
    )
    return "".join(p.capitalize() for p in parts if p)


# TODO: Replace with lif.string_utils function
def to_pascal_case(parts):
    """Join list of strings as PascalCase."""
    return "".join(p.capitalize() for p in parts if p)


# TODO: Update docstring
def unique_type_name(name: str, suffix: str, root_node: str) -> str:
    """Make a unique PascalCase type name with suffix."""
    parts = re.split(r"\W+", name)
    root = to_pascal_case_from_str(root_node)
    if parts and to_pascal_case_from_str(parts[0]) == root:
        parts = parts[1:]
    if not parts:
        parts = [root]
    return f"{to_pascal_case(parts)}{suffix[:1].upper() + suffix[1:]}"


def _iso(obj: Union[_dt.date, _dt.datetime]) -> str:
    """Return date/datetime as ISO-8601 string."""
    return obj.isoformat()


def serialize_for_json(obj: Any) -> Any:
    """Convert obj into JSON-serialisable structures."""
    if hasattr(obj, "model_dump"):
        return serialize_for_json(obj.model_dump(exclude_none=True))
    if dataclasses.is_dataclass(obj):
        return serialize_for_json(dataclasses.asdict(obj))
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, (_dt.datetime, _dt.date)):
        return _iso(obj)
    if isinstance(obj, (list, tuple)):
        return [serialize_for_json(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): serialize_for_json(v) for k, v in obj.items()}
    return obj


def get_fragments_from_info(info: strawberry.types.Info) -> Dict[str, Any]:
    """Return fragments map from GraphQL info object."""
    return getattr(info, "fragments", {})


def get_selected_field_paths(
    field_nodes: List[Any],
    fragments: Dict[str, Any],
    prefix: Optional[Union[List[str], str]] = None,
) -> List[str]:
    """Get dotted JSON paths actually requested in the selection."""
    prefix = [] if prefix is None else ([prefix] if isinstance(prefix, str) else prefix)
    paths: set[str] = set()

    for node in field_nodes:
        sel_set = getattr(node, "selection_set", None)
        if not sel_set:
            continue
        for selection in sel_set.selections:
            match selection.kind:
                case "field":
                    path = prefix + [selection.name.value]
                    paths.add(".".join(path))
                    paths.update(get_selected_field_paths([selection], fragments, path))
                case "fragment_spread":
                    frag = fragments[selection.name.value]
                    paths.update(get_selected_field_paths([frag], fragments, prefix))
    return list(paths)