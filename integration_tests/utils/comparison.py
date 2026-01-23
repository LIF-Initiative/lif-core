"""Data comparison utilities for integration tests.

Provides verbose diffing to help track down data discrepancies between layers.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Difference:
    """Represents a single difference between expected and actual data."""

    path: str
    expected: Any
    actual: Any
    diff_type: str  # "missing", "extra", "value_mismatch", "type_mismatch"

    def __str__(self) -> str:
        if self.diff_type == "missing":
            return f"MISSING  {self.path}: expected {self.expected!r}"
        elif self.diff_type == "extra":
            return f"EXTRA    {self.path}: found {self.actual!r}"
        elif self.diff_type == "type_mismatch":
            return f"TYPE     {self.path}: expected {type(self.expected).__name__}, got {type(self.actual).__name__}"
        else:
            return f"MISMATCH {self.path}: expected {self.expected!r}, got {self.actual!r}"


@dataclass
class ComparisonResult:
    """Result of comparing expected vs actual data."""

    person_name: str
    org_id: str
    layer: str  # "mongodb", "query_cache", "graphql", etc.
    differences: list[Difference] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.differences) == 0

    def format_report(self, max_diffs: int = 20) -> str:
        """Format a human-readable report of differences."""
        if self.passed:
            return f"[PASS] {self.org_id}/{self.person_name} @ {self.layer}"

        lines = [
            f"[FAIL] {self.org_id}/{self.person_name} @ {self.layer}",
            f"       {len(self.differences)} difference(s) found:",
        ]

        shown = self.differences[:max_diffs]
        for diff in shown:
            lines.append(f"         - {diff}")

        if len(self.differences) > max_diffs:
            lines.append(f"         ... and {len(self.differences) - max_diffs} more")

        return "\n".join(lines)


def _compare_values(
    expected: Any,
    actual: Any,
    path: str,
    differences: list[Difference],
    ignore_keys: set[str] | None = None,
) -> None:
    """Recursively compare two values, collecting differences."""
    ignore_keys = ignore_keys or set()

    # Handle None cases
    if expected is None and actual is None:
        return
    if expected is None:
        differences.append(Difference(path, expected, actual, "extra"))
        return
    if actual is None:
        differences.append(Difference(path, expected, actual, "missing"))
        return

    # Type mismatch
    if type(expected) != type(actual):
        # Allow int/float comparison
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            if expected != actual:
                differences.append(Difference(path, expected, actual, "value_mismatch"))
            return
        differences.append(Difference(path, expected, actual, "type_mismatch"))
        return

    # Dict comparison
    if isinstance(expected, dict):
        all_keys = set(expected.keys()) | set(actual.keys())
        for key in all_keys:
            if key in ignore_keys:
                continue
            new_path = f"{path}.{key}" if path else key
            if key not in expected:
                differences.append(Difference(new_path, None, actual[key], "extra"))
            elif key not in actual:
                differences.append(Difference(new_path, expected[key], None, "missing"))
            else:
                _compare_values(expected[key], actual[key], new_path, differences, ignore_keys)
        return

    # List comparison
    if isinstance(expected, list):
        if len(expected) != len(actual):
            differences.append(
                Difference(
                    f"{path}[len]",
                    len(expected),
                    len(actual),
                    "value_mismatch",
                )
            )
        for i, (exp_item, act_item) in enumerate(zip(expected, actual)):
            _compare_values(exp_item, act_item, f"{path}[{i}]", differences, ignore_keys)
        return

    # Scalar comparison
    if expected != actual:
        differences.append(Difference(path, expected, actual, "value_mismatch"))


def compare_person_data(
    expected: dict[str, Any],
    actual: dict[str, Any],
    person_name: str,
    org_id: str,
    layer: str,
    ignore_keys: set[str] | None = None,
) -> ComparisonResult:
    """Compare expected Person data against actual data from a service layer.

    Args:
        expected: Expected data (from sample files)
        actual: Actual data (from service layer)
        person_name: Name of the person being compared (for reporting)
        org_id: Organization ID (for reporting)
        layer: Service layer name (for reporting)
        ignore_keys: Optional set of keys to ignore during comparison

    Returns:
        ComparisonResult with list of differences
    """
    differences: list[Difference] = []
    _compare_values(expected, actual, "", differences, ignore_keys)
    return ComparisonResult(
        person_name=person_name,
        org_id=org_id,
        layer=layer,
        differences=differences,
    )


def format_diff(expected: Any, actual: Any, context_lines: int = 3) -> str:
    """Format a side-by-side diff of two values.

    Useful for debugging specific mismatches.
    """
    import json

    exp_str = json.dumps(expected, indent=2, default=str)
    act_str = json.dumps(actual, indent=2, default=str)

    exp_lines = exp_str.splitlines()
    act_lines = act_str.splitlines()

    lines = ["=" * 60]
    lines.append("EXPECTED:")
    lines.extend(f"  {line}" for line in exp_lines[:50])
    if len(exp_lines) > 50:
        lines.append(f"  ... ({len(exp_lines) - 50} more lines)")

    lines.append("-" * 60)
    lines.append("ACTUAL:")
    lines.extend(f"  {line}" for line in act_lines[:50])
    if len(act_lines) > 50:
        lines.append(f"  ... ({len(act_lines) - 50} more lines)")

    lines.append("=" * 60)
    return "\n".join(lines)


def summarize_results(results: list[ComparisonResult]) -> str:
    """Summarize a list of comparison results."""
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    lines = [
        "",
        "=" * 60,
        f"SUMMARY: {passed} passed, {failed} failed",
        "=" * 60,
    ]

    if failed > 0:
        lines.append("")
        lines.append("FAILURES:")
        for result in results:
            if not result.passed:
                lines.append(result.format_report())
                lines.append("")

    return "\n".join(lines)
