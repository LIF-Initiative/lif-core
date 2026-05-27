"""Seed dummy env vars so importing `lif.mdr_utils.database_setup` doesn't
fail at engine-construction time when running these unit tests.

The tests in this directory exercise pure-Python helpers (e.g.
`_redact_url`); they never actually connect to a database. We just need
the module-level `DATABASE_URL` + `create_async_engine` calls to succeed.
"""

import os

os.environ.setdefault("POSTGRESQL_USER", "test")
os.environ.setdefault("POSTGRESQL_PASSWORD", "test")
os.environ.setdefault("POSTGRESQL_HOST", "localhost")
os.environ.setdefault("POSTGRESQL_PORT", "5432")
os.environ.setdefault("POSTGRESQL_DB", "test")
