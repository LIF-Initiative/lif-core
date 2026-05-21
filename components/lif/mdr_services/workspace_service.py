"""Workspace listing for MDR self-serve (issue #884 Phase 3 PR 1).

Pure helpers — given a list of Cognito groups (from the JWT
``cognito:groups`` claim), build the list of workspaces the user has
access to. Each workspace is a (group, tenant_schema) pair.

Schema existence is *not* verified here; the post-confirmation Lambda
provisions a schema for every group it creates, so a group claim that
sanitizes to a valid schema name is treated as a usable workspace. If a
group somehow exists in Cognito without a matching PG schema, queries
against it will fail loudly at session time — that's the right place to
surface the divergence rather than papering over it in this listing.
"""

from dataclasses import dataclass

from pydantic import BaseModel

from lif.tenant_routing import tenant_schema_for_group


@dataclass(frozen=True)
class Workspace:
    """A tenant workspace the caller has access to."""

    group: str
    tenant_schema: str


class WorkspaceItem(BaseModel):
    """API response shape for a workspace.

    Separate from the internal ``Workspace`` dataclass so the wire
    contract can evolve independently of in-process types — e.g., we
    might later add ``display_name`` or ``schema_status`` to the API
    without changing the service-layer return shape.
    """

    group: str
    tenant_schema: str


def to_workspace_item(workspace: Workspace) -> WorkspaceItem:
    """Project a service-layer ``Workspace`` into its API response shape."""
    return WorkspaceItem(group=workspace.group, tenant_schema=workspace.tenant_schema)


def list_workspaces_for_groups(cognito_groups: list[str] | None) -> list[Workspace]:
    """Map Cognito groups to the user's accessible workspaces.

    Skips groups that sanitize to an empty schema name (e.g., punctuation-
    only group names that shouldn't have produced a tenant in the first
    place). Preserves Cognito's group ordering so the first entry matches
    the default-fallback used by ``resolve_tenant_schema``.
    """
    if not cognito_groups:
        return []
    workspaces: list[Workspace] = []
    for group in cognito_groups:
        schema = tenant_schema_for_group(group)
        if schema is None:
            continue
        workspaces.append(Workspace(group=group, tenant_schema=schema))
    return workspaces


def find_workspace(cognito_groups: list[str] | None, group: str) -> Workspace | None:
    """Return the Workspace for ``group`` if and only if the caller has access.

    Used by the /tenants/select endpoint and the auth middleware's cookie
    validator: in both cases, the caller proposes a group name and we need
    to confirm it's actually one of theirs (defense in depth — the Cognito
    JWT is the source of truth for group membership; never trust the
    client's request body or cookie alone).
    """
    if not cognito_groups or group not in cognito_groups:
        return None
    schema = tenant_schema_for_group(group)
    if schema is None:
        return None
    return Workspace(group=group, tenant_schema=schema)
