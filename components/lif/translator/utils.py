from copy import deepcopy
from typing import List


def deep_merge(dst, src):
    """
    Merge src into dst in place.
    - dicts: recursive merge
    - lists of dicts: merge element-by-element by index
      (e.g., multiple mappings that each produce [{"caption": ...}],
       [{"imageId": ...}] will merge into one list item with all keys)
    - lists (non-dicts): append unique items
    - scalars: overwrite
    """
    for k, v in src.items():
        if k not in dst:
            dst[k] = deepcopy(v)
            continue

        dv = dst[k]
        # dict into dict -> recurse
        if isinstance(dv, dict) and isinstance(v, dict):
            deep_merge(dv, v)
        # list into list
        elif isinstance(dv, list) and isinstance(v, list):
            if all(isinstance(x, dict) for x in dv) and all(isinstance(x, dict) for x in v):
                # merge dict elements by index
                for i, sv in enumerate(v):
                    if i < len(dv):
                        deep_merge(dv[i], sv)
                    else:
                        dv.append(deepcopy(sv))
            else:
                # append unique primitives or mixed
                for item in v:
                    if item not in dv:
                        dv.append(deepcopy(item))
        else:
            # different types or scalar -> overwrite
            dst[k] = deepcopy(v)
    return dst


def convert_transformation_to_mappings(transformation: dict) -> List[str]:
    expressions: List[str] = []
    for item in transformation.get("data", []):
        transformation_expression: str | None = item.get("TransformationExpression")
        if transformation_expression:
            expressions.append(transformation_expression)
    return expressions
