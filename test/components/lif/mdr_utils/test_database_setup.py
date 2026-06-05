"""Unit tests for `database_setup._redact_url` — issue #938.

The full `database_setup` module imports SQLAlchemy/asyncpg/etc at import
time and tries to construct an engine from env vars, so we import the
helper directly rather than the whole module via the package surface."""

from lif.mdr_utils.database_setup import _redact_url


class TestRedactUrl:
    def test_masks_password_in_typical_postgres_url(self):
        url = "postgresql+asyncpg://postgres:s3cret!@dbhost.example:5432/mydb"
        assert _redact_url(url) == "postgresql+asyncpg://postgres:***@dbhost.example:5432/mydb"

    def test_masks_password_with_special_characters(self):
        # Real dev password observed in CloudWatch had `:`, `}`, `&`, `<`, `$`
        # in it. urlparse handles percent-encoding; here we use a
        # representative literal to confirm the redaction doesn't choke.
        url = "postgresql+asyncpg://postgres:p:%24sw0rd@host:5432/db"
        redacted = _redact_url(url)
        assert "p:%24sw0rd" not in redacted
        assert "postgres:***@host:5432/db" in redacted

    def test_url_without_port_still_redacts(self):
        url = "postgresql+asyncpg://postgres:s3cret@host/db"
        # No explicit port — netloc is just user:pass@host. Redacted form
        # must drop the password but keep everything else.
        redacted = _redact_url(url)
        assert "s3cret" not in redacted
        assert "postgres:***@host" in redacted
        assert "/db" in redacted

    def test_url_without_password_is_unchanged(self):
        # IAM-auth style (no password), or local trust auth — we return
        # the original string rather than mangling it.
        url = "postgresql+asyncpg://postgres@host:5432/db"
        assert _redact_url(url) == url

    def test_unparseable_input_does_not_raise(self):
        # The function is only ever called for logging; if it raises,
        # MDR startup fails. Return a sentinel string instead so the
        # log line still emits something operator-readable.
        # urlparse is famously tolerant — `urlparse("")` returns an
        # empty ParseResult rather than raising — so this test really
        # documents the "no exception" guarantee.
        assert _redact_url("") == ""
        assert _redact_url("not-a-url") == "not-a-url"
