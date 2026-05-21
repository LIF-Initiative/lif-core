"""Unit tests for workspace_service — pure helpers, no DB."""

from lif.mdr_services.workspace_service import Workspace, find_workspace, list_workspaces_for_groups


class TestListWorkspacesForGroups:
    def test_empty_for_no_groups(self):
        assert list_workspaces_for_groups(None) == []
        assert list_workspaces_for_groups([]) == []

    def test_maps_group_to_tenant_schema(self):
        result = list_workspaces_for_groups(["lif-team"])
        assert result == [Workspace(group="lif-team", tenant_schema="tenant_lif_team")]

    def test_preserves_cognito_group_ordering(self):
        """resolve_tenant_schema's default fallback uses cognito_groups[0];
        we must keep the same order so the listed first item matches the
        default the middleware will pick when no cookie is set."""
        result = list_workspaces_for_groups(["acme-univ", "lif-team", "eval-jsmith"])
        assert [w.group for w in result] == ["acme-univ", "lif-team", "eval-jsmith"]

    def test_skips_groups_that_sanitize_to_empty(self):
        """A punctuation-only group name shouldn't have produced a tenant —
        skip it from the listing rather than returning a schema-less entry."""
        result = list_workspaces_for_groups(["lif-team", "---", "acme-univ"])
        assert [w.group for w in result] == ["lif-team", "acme-univ"]


class TestFindWorkspace:
    def test_returns_workspace_when_group_in_cognito_groups(self):
        result = find_workspace(["lif-team", "acme-univ"], "acme-univ")
        assert result == Workspace(group="acme-univ", tenant_schema="tenant_acme_univ")

    def test_returns_none_when_group_not_in_cognito_groups(self):
        """Defense in depth — the user's JWT groups are the ground truth.
        If the proposed group isn't there, refuse rather than trust client
        input."""
        assert find_workspace(["lif-team"], "acme-univ") is None

    def test_returns_none_for_empty_groups(self):
        assert find_workspace(None, "lif-team") is None
        assert find_workspace([], "lif-team") is None

    def test_returns_none_when_group_sanitizes_to_empty(self):
        """Even if --- somehow ended up in cognito_groups, we shouldn't
        route a request to an empty tenant_ schema."""
        assert find_workspace(["---"], "---") is None
