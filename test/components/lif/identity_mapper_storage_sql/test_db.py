from os import getenv

import pytest

from lif.identity_mapper_storage_sql import db


def test_parse_connect_args_defaults_to_empty_dict():
    assert db.parse_connect_args(None) == {}
    assert db.parse_connect_args("") == {}


def test_parse_connect_args_returns_a_dict():
    assert db.parse_connect_args('{"ssl": {"ca": "/certs/ca.pem"}}') == {"ssl": {"ca": "/certs/ca.pem"}}


@pytest.mark.parametrize("raw", ["not json", '"a string"', "[1, 2]"])
def test_parse_connect_args_rejects_non_objects(raw):
    with pytest.raises(ValueError, match="must be a JSON object"):
        db.parse_connect_args(raw)


@pytest.mark.skipif(
    getenv("IDENTITY_MAPPER_DB_POOL_PRE_PING") is not None, reason="the default only applies when the variable is unset"
)
def test_pool_pre_ping_defaults_on():
    """
    The startup SELECT 1 is gone and the pool is larger, so connections idle past
    MariaDB's wait_timeout unless they are validated on checkout. Read at import, so this
    asserts the module constant rather than re-reading the environment.
    """
    assert db.db_pool_pre_ping is True


# === Async-driver validation (Issue #1199) ===================================


@pytest.mark.parametrize("driver", ["mysql+pymysql", "mysql", "mysql+mysqldb", "mariadb+pymysql"])
def test_require_async_driver_rejects_sync_drivers_by_name(driver):
    """The message must name the variable and the value to set.

    SQLAlchemy's own error ("The loaded 'pymysql' is not async") names neither, and this
    is the exact failure an environment hits when the image is deployed ahead of its task
    definition -- so a cryptic error here costs a debugging session.
    """
    with pytest.raises(ValueError) as raised:
        db.require_async_driver(driver)
    message = str(raised.value)
    assert "IDENTITY_MAPPER_DB_DRIVER" in message
    assert driver in message
    assert "mysql+asyncmy" in message


@pytest.mark.parametrize("driver", ["mysql+asyncmy", "postgresql+asyncpg", "sqlite+aiosqlite"])
def test_require_async_driver_accepts_async_drivers(driver):
    db.require_async_driver(driver)


def test_require_async_driver_defers_unknown_drivers_to_engine_creation():
    """An unrecognized driver is not this check's error to explain; engine creation
    already raises NoSuchModuleError naming the module it could not load."""
    db.require_async_driver("mysql+missing")


def test_validate_db_environment_rejects_a_sync_driver(monkeypatch):
    """The check is wired into validation, not merely defined."""
    monkeypatch.setattr(db, "db_driver_name", "mysql+pymysql")
    monkeypatch.setattr(db, "db_username", "u")
    monkeypatch.setattr(db, "db_password", "p")
    monkeypatch.setattr(db, "db_host", "h")
    with pytest.raises(ValueError, match="requires an async driver"):
        db.validate_db_environment()
