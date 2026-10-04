import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from lif.identity_mapper_storage_sql.core import IdentityMapperSqlStorage
from lif.identity_mapper_storage_sql.db import Base


@pytest.fixture()
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture()
async def session_factory(db_engine):
    return async_sessionmaker(expire_on_commit=False, autoflush=False, bind=db_engine)


@pytest.fixture()
async def session(session_factory):
    async with session_factory() as s:
        async with s.begin():
            yield s


@pytest.fixture()
async def storage(session_factory):
    return IdentityMapperSqlStorage(session_factory)
