"""Test-session environment defaults.

Some modules deliberately have **no fallback** for security-sensitive settings —
a default in product code would make insecurity the default, so they raise at
import time when the variable is missing (see #1191). That is the behavior we
want in every real environment, but it means the test session has to supply the
values itself.

Setting them here, rather than re-adding defaults to the product code, keeps the
fail-fast guarantee where it matters and confines the test-only values to tests.
`conftest.py` at the test root is imported before any test module is collected,
so these are in place before the guards run.

Values are obvious throwaways and must never be used anywhere else.
"""

import os

_TEST_ONLY_ENV = {
    # Signs/verifies JWTs in components/lif/auth
    "SECRET_KEY": "test-only-not-a-real-secret",
    # Demo login password in the advisor and MDR bases
    "LIF_DEMO_USER_PASSWORD": "test-only-not-a-real-password",
}

for _name, _value in _TEST_ONLY_ENV.items():
    os.environ.setdefault(_name, _value)
