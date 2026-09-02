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
