"""Re-export the public API so callers can `from lif.tenant_routing import ...`.

Matches the polylith convention where a component's surface lives in
``core.py`` and ``__init__.py`` makes it importable as a flat name.
"""

from lif.tenant_routing.core import (
    MAX_GROUP_NAME_LEN,
    SCHEMA_PREFIX,
    resolve_tenant_schema,
    sanitize_group_name,
    tenant_schema_for_group,
)

__all__ = [
    "MAX_GROUP_NAME_LEN",
    "SCHEMA_PREFIX",
    "resolve_tenant_schema",
    "sanitize_group_name",
    "tenant_schema_for_group",
]
