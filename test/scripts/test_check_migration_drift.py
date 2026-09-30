"""Tests for the migration-drift script's repo-side logic (#1226).

`repo_versions()` is pure and has edge cases worth pinning: numeric rather than string
ordering, multi-digit minors, and repeatable migrations which carry no version at all.
The script previously used hyphens in its filename, which made it un-importable and so
untestable without importlib gymnastics.
"""

import importlib.util
import pathlib

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_migration_drift.py"
_spec = importlib.util.spec_from_file_location("check_migration_drift", _SCRIPT)
drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drift)


def _make(tmp_path, *names):
    for name in names:
        (tmp_path / name).write_text("-- test\n")
    return tmp_path


def test_versions_sort_numerically_not_lexically(tmp_path):
    """V1.10 comes after V1.2. String sorting gets this backwards."""
    _make(tmp_path, "V1.2__a.sql", "V1.10__b.sql", "V1.9__c.sql")
    assert drift.repo_versions(tmp_path) == ["1.2", "1.9", "1.10"]


def test_a_future_major_version_sorts_last(tmp_path):
    _make(tmp_path, "V1.6__a.sql", "V2.0__b.sql", "V1.10__c.sql")
    assert drift.repo_versions(tmp_path) == ["1.6", "1.10", "2.0"]


def test_repeatable_migrations_are_not_treated_as_versions(tmp_path):
    """R__ has no version, so 'is it applied' does not apply -- but it must not vanish."""
    _make(tmp_path, "V1.0__a.sql", "R__refresh_views.sql")
    assert drift.repo_versions(tmp_path) == ["1.0"]
    assert drift.repeatable_migrations(tmp_path) == ["R__refresh_views.sql"]


def test_non_migration_files_are_ignored(tmp_path):
    _make(tmp_path, "V1.0__a.sql", "README.md", "V_not_a_version__b.sql")
    assert drift.repo_versions(tmp_path) == ["1.0"]


def test_the_live_migration_directory_parses(tmp_path):
    """Guard against the repo's own filenames drifting out of the expected shape."""
    versions = drift.repo_versions()
    assert versions, "no migrations found -- has the directory moved?"
    assert versions == sorted(versions, key=drift.version_key)


@pytest.mark.parametrize("version,expected", [("1.6", [1, 6]), ("1.10", [1, 10]), ("2", [2])])
def test_version_key(version, expected):
    assert drift.version_key(version) == expected
