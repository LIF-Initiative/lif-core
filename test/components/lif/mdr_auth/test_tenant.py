"""Tests for tenant-schema resolution (issue #883).

These are pure-function tests — no middleware, no DB, no Cognito.
The middleware integration (that `request.state.tenant_schema` actually
gets set) is covered separately in test_middleware.py.
"""

import pytest
from lif.mdr_auth.tenant import MAX_GROUP_NAME_LEN, resolve_tenant_schema, sanitize_group_name, tenant_schema_for_group


class TestSanitizeGroupName:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            # Common Cognito group shapes we'll actually see
            ("lif-team", "lif_team"),
            ("eval-jsmith", "eval_jsmith"),
            ("acme-univ", "acme_univ"),
            ("Acme University", "acme_university"),
            # Case-insensitive; leading/trailing whitespace stripped
            ("LIF_TEAM", "lif_team"),
            ("  eval-jsmith  ", "eval_jsmith"),
            # Non-identifier runs collapse to a single underscore
            ("a---b", "a_b"),
            ("a  b  c", "a_b_c"),
            # Empty/no-letter inputs resolve to empty so caller falls back
            ("", ""),
            ("---", ""),
            ("123", ""),
        ],
    )
    def test_sanitizes(self, raw, expected):
        assert sanitize_group_name(raw) == expected

    def test_strips_leading_non_letters(self):
        """Leading digits or underscores removed so the result is a valid PG identifier start."""
        assert sanitize_group_name("_foo") == "foo"
        assert sanitize_group_name("9lives") == "lives"
        # Internal double-underscores are preserved — they're valid PG identifiers
        # and we want schema names to round-trip back to the group name predictably.
        assert sanitize_group_name("__bar__baz") == "bar__baz"

    def test_truncates_to_max_length(self):
        """Long group names truncate at MAX_GROUP_NAME_LEN so tenant_{name} fits PG's 63-char limit."""
        long_group = "a" * 200
        result = sanitize_group_name(long_group)
        assert len(result) == MAX_GROUP_NAME_LEN
        # tenant_ prefix (7) + result (55) = 62 chars, fits the 63-char limit
        assert len(f"tenant_{result}") <= 63


class TestTenantSchemaForGroup:
    def test_builds_tenant_prefixed_schema(self):
        assert tenant_schema_for_group("lif-team") == "tenant_lif_team"

    def test_returns_none_when_group_sanitizes_empty(self):
        """Guard against constructing ``tenant_`` with no suffix — caller must fall back."""
        assert tenant_schema_for_group("---") is None
        assert tenant_schema_for_group("") is None
        assert tenant_schema_for_group("123") is None


class TestResolveTenantSchema:
    def test_flag_off_always_returns_none(self):
        """With the feature flag off this must be a no-op — that's how PR 2 ships as dead-code-behind-a-flag."""
        assert (
            resolve_tenant_schema(
                enabled=False, is_service_principal=False, cognito_groups=["lif-team"], service_schema="tenant_lif_team"
            )
            is None
        )
        # Also None for service principals when flag is off
        assert (
            resolve_tenant_schema(
                enabled=False, is_service_principal=True, cognito_groups=None, service_schema="tenant_lif_team"
            )
            is None
        )

    def test_service_principal_routes_to_service_schema(self):
        """API-key callers (graphql, semantic-search, translator) all share one schema."""
        assert (
            resolve_tenant_schema(
                enabled=True, is_service_principal=True, cognito_groups=None, service_schema="tenant_lif_team"
            )
            == "tenant_lif_team"
        )

    def test_cognito_user_with_group_routes_to_tenant_schema(self):
        assert (
            resolve_tenant_schema(
                enabled=True,
                is_service_principal=False,
                cognito_groups=["eval-jsmith"],
                service_schema="tenant_lif_team",
            )
            == "tenant_eval_jsmith"
        )

    def test_first_group_wins_when_user_has_multiple(self):
        """Until the workspace selector lands (phase 3), first-group-wins is the documented rule."""
        assert (
            resolve_tenant_schema(
                enabled=True,
                is_service_principal=False,
                cognito_groups=["acme-univ", "lif-team"],
                service_schema="tenant_lif_team",
            )
            == "tenant_acme_univ"
        )

    def test_cognito_user_no_group_falls_back_to_service_schema(self):
        """A Cognito user who somehow has no group shouldn't get a 500 — fall back like an API-key caller."""
        assert (
            resolve_tenant_schema(
                enabled=True, is_service_principal=False, cognito_groups=[], service_schema="tenant_lif_team"
            )
            == "tenant_lif_team"
        )
        assert (
            resolve_tenant_schema(
                enabled=True, is_service_principal=False, cognito_groups=None, service_schema="tenant_lif_team"
            )
            == "tenant_lif_team"
        )

    def test_group_that_sanitizes_to_empty_falls_back(self):
        """A group of only digits/punctuation shouldn't produce ``tenant_`` with no suffix."""
        assert (
            resolve_tenant_schema(
                enabled=True, is_service_principal=False, cognito_groups=["---"], service_schema="tenant_lif_team"
            )
            == "tenant_lif_team"
        )
