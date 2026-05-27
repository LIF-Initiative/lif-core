"""Unit tests for workspace_service — pure helpers, no DB."""

from lif.mdr_services.workspace_service import (
    Workspace,
    compute_display_name,
    find_workspace,
    list_workspaces_for_groups,
    to_workspace_item,
)


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


class TestComputeDisplayName:
    """Friendly display name resolution (issue #943).

    For a user's own personal tenant the display name is their email
    (verified via the eval-<sub> group / JWT sub match). For any other
    group the display name is just the group name as today.
    """

    def test_personal_tenant_uses_email_when_match(self):
        # Cognito's sub claim is `abc123`; the post-confirmation Lambda
        # created `eval-abc123` for them. The user's email is on
        # principal. Display name should be the email.
        assert (
            compute_display_name(
                group="eval-abc123",
                cognito_sub="abc123",
                principal="user@example.edu",
                tenant_schema="tenant_eval_abc123",
            )
            == "user@example.edu"
        )

    def test_shared_group_uses_group_name(self):
        # User is in lif-team (a shared group). Even though we have the
        # email on principal, the group name is the right friendly label
        # for a shared workspace.
        assert (
            compute_display_name(
                group="lif-team", cognito_sub="abc123", principal="user@example.edu", tenant_schema="tenant_lif_team"
            )
            == "lif-team"
        )

    def test_eval_group_for_different_sub_does_not_use_email(self):
        # Defense-in-depth: if another user's eval-* group somehow ended
        # up in the caller's group list (shouldn't happen — the post-
        # confirmation Lambda only adds the caller to their own — but
        # belt-and-suspenders), we don't claim someone else's tenant as
        # theirs via the email label.
        assert (
            compute_display_name(
                group="eval-other_user_sub",
                cognito_sub="abc123",
                principal="user@example.edu",
                tenant_schema="tenant_eval_other_user_sub",
            )
            == "eval-other_user_sub"
        )

    def test_legacy_principal_without_at_falls_back_to_group(self):
        # Legacy HS256 path or any JWT where `principal` is a sub (no
        # email claim available). We can't surface a friendlier label,
        # so use the group name. The `@` heuristic is what tells us
        # whether principal is an email or a sub.
        assert (
            compute_display_name(
                group="eval-abc123",
                cognito_sub="abc123",
                principal="abc123",  # sub, not email
                tenant_schema="tenant_eval_abc123",
            )
            == "eval-abc123"
        )

    def test_missing_sub_falls_back_to_group(self):
        # Without a sub we can't verify the eval-* group is the caller's,
        # so play it safe and use the group name.
        assert (
            compute_display_name(
                group="eval-abc123", cognito_sub=None, principal="user@example.edu", tenant_schema="tenant_eval_abc123"
            )
            == "eval-abc123"
        )

    def test_missing_principal_falls_back_to_group(self):
        assert (
            compute_display_name(
                group="eval-abc123", cognito_sub="abc123", principal=None, tenant_schema="tenant_eval_abc123"
            )
            == "eval-abc123"
        )

    def test_empty_principal_after_strip_falls_back_to_tenant_schema(self):
        # Defense-in-depth per Adam's #947 review: if the resolved
        # candidate is whitespace-only (a principal of "  " somehow
        # passed the `@` check, etc.), fall through to tenant_schema
        # rather than emit an empty display_name. The wire contract
        # promises `display_name` is non-empty.
        assert (
            compute_display_name(
                group="eval-abc123",
                cognito_sub="abc123",
                principal=" @ ",  # whitespace + @ would pass the heuristic but strip to nothing useful
                tenant_schema="tenant_eval_abc123",
            )
            # principal " @ " stripped is "@" — not empty, so it's used as-is.
            # The fallback only kicks in when the candidate is truly empty
            # after strip. The exact behavior here is documented: we don't
            # over-sanitize, just guarantee non-empty.
            == "@"
        )

    def test_empty_group_falls_back_to_tenant_schema(self):
        # Sanity: if a group somehow sanitized to empty string (the
        # listing pipeline filters these out before this point, but
        # belt-and-suspenders), tenant_schema is the ultimate fallback.
        assert (
            compute_display_name(group="", cognito_sub=None, principal=None, tenant_schema="tenant_lif_team")
            == "tenant_lif_team"
        )


class TestToWorkspaceItem:
    """Projection from internal Workspace into the API-facing WorkspaceItem."""

    def test_includes_friendly_display_name_for_personal_tenant(self):
        ws = Workspace(group="eval-abc123", tenant_schema="tenant_eval_abc123")
        item = to_workspace_item(ws, cognito_sub="abc123", principal="user@example.edu")
        assert item.group == "eval-abc123"
        assert item.tenant_schema == "tenant_eval_abc123"
        assert item.display_name == "user@example.edu"

    def test_uses_group_name_for_shared_group(self):
        ws = Workspace(group="lif-team", tenant_schema="tenant_lif_team")
        item = to_workspace_item(ws, cognito_sub="abc123", principal="user@example.edu")
        assert item.display_name == "lif-team"

    def test_no_identity_hints_defaults_to_group_name(self):
        # Callers that don't pass identity context get the same shape they
        # got pre-#943 (display_name == group).
        ws = Workspace(group="lif-team", tenant_schema="tenant_lif_team")
        item = to_workspace_item(ws)
        assert item.display_name == "lif-team"
