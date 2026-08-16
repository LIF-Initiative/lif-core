import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from lif.identity_mapper_storage_sql.core import IdentityMapperSqlStorage
from lif.identity_mapper_storage_sql.db import Base


@pytest.fixture()
def db_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture()
def session_factory(db_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=db_engine)


@pytest.fixture()
def session(session_factory):
    with session_factory() as s:
        with s.begin():
            yield s


@pytest.fixture()
def storage(session_factory):
    return IdentityMapperSqlStorage(session_factory)
