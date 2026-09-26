import json
from logging import DEBUG
from os import getenv
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.engine import URL
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import declarative_base

from lif.logging.core import get_logger


db_driver_name: str | None = getenv("IDENTITY_MAPPER_DB_DRIVER")
db_connect_args: str | None = getenv("IDENTITY_MAPPER_DB_CONNECT_ARGS")
db_username: str | None = getenv("IDENTITY_MAPPER_DB_USERNAME")
db_password: str | None = getenv("IDENTITY_MAPPER_DB_PASSWORD")
db_host: str | None = getenv("IDENTITY_MAPPER_DB_HOST")
db_port: str = getenv("IDENTITY_MAPPER_DB_PORT", "3306")
db_name: str = getenv("IDENTITY_MAPPER_DB_NAME", "lif")
db_auto_create_tables: bool = getenv("IDENTITY_MAPPER_DB_AUTO_CREATE_TABLES", "false").lower() == "true"
db_pool_size: int = int(getenv("IDENTITY_MAPPER_DB_POOL_SIZE", "10"))
db_pool_pre_ping: bool = getenv("IDENTITY_MAPPER_DB_POOL_PRE_PING", "true").lower() == "true"


logger = get_logger(__name__)
engine: AsyncEngine | None = None
sessionFactory: async_sessionmaker | None = None
Base = declarative_base()


# Sync drivers this brick used to run on, mapped to the async driver that replaces them,
# so the error below can name the value to set rather than only the one that is wrong.
ASYNC_DRIVER_REPLACEMENTS: dict[str, str] = {
    "mysql": "mysql+asyncmy",
    "mysql+pymysql": "mysql+asyncmy",
    "mysql+mysqldb": "mysql+asyncmy",
    "mariadb": "mysql+asyncmy",
    "mariadb+pymysql": "mysql+asyncmy",
}


def require_async_driver(driver_name: str) -> None:
    """
    Fail with an actionable message when configured with a synchronous driver.

    Since #1199 this brick runs async SQLAlchemy, so a sync driver cannot work at all:
    `create_async_engine` raises "The loaded 'pymysql' is not async" from inside the
    FastAPI lifespan. That error never names the environment variable to change, and it
    is the failure an environment hits whenever the image is deployed ahead of its task
    definition -- CI redeploys the image on merge but only `aws-deploy.sh` applies
    `cloudformation/lif-identity-mapper-taskdef-includes.yml`. Say plainly what to set.
    """
    try:
        is_async = make_url(f"{driver_name}://").get_dialect().is_async
    except Exception:
        # Unknown or missing driver: not our error to explain. Let engine creation raise
        # its own, which already names the module it could not load.
        return
    if is_async:
        return
    replacement = ASYNC_DRIVER_REPLACEMENTS.get(driver_name)
    hint = f" Set it to '{replacement}'." if replacement else " Use an async driver."
    raise ValueError(
        f"IDENTITY_MAPPER_DB_DRIVER is '{driver_name}', a synchronous driver. This service uses "
        f"async SQLAlchemy and requires an async driver.{hint} A deployed task definition or "
        "compose file still carrying the old value needs updating (see issue #1199)."
    )


def validate_db_environment() -> None:
    if not db_driver_name or not db_username or not db_password or not db_host:
        raise ValueError("Database configuration environment variables are not set properly")
    require_async_driver(db_driver_name)


def create_db_connection_url() -> URL:
    return URL.create(
        drivername=db_driver_name if db_driver_name else "",
        username=db_username,
        password=db_password,
        host=db_host,
        port=int(db_port),
        database=db_name,
    )


def parse_connect_args(raw: str | None) -> dict:
    """
    IDENTITY_MAPPER_DB_CONNECT_ARGS arrives as a string but SQLAlchemy wants a dict.
    Parsed here rather than at import so a malformed value fails engine creation with a
    clear message instead of breaking the module import.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError("IDENTITY_MAPPER_DB_CONNECT_ARGS must be a JSON object") from e
    if not isinstance(parsed, dict):
        raise ValueError("IDENTITY_MAPPER_DB_CONNECT_ARGS must be a JSON object")
    return parsed


def create_db_engine():
    validate_db_environment()
    url: URL = create_db_connection_url()
    global engine
    engine = create_async_engine(
        url, connect_args=parse_connect_args(db_connect_args), pool_size=db_pool_size, pool_pre_ping=db_pool_pre_ping
    )


def create_db_session_factory():
    global sessionFactory
    if engine is None:
        raise ValueError("Engine is not initialized. Call create_db_engine() first.")
    sessionFactory = async_sessionmaker(expire_on_commit=False, autoflush=False, bind=engine)


async def initialize_database() -> None:
    create_db_engine()
    create_db_session_factory()
    await log_database_ddl()
    if db_auto_create_tables:
        db_engine = engine
        if db_engine is None:
            raise ValueError("Engine is not initialized. Call create_db_engine() first.")
        async with db_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")


def get_db_session_factory() -> async_sessionmaker:
    if sessionFactory is None:
        raise ValueError("Session Factory is not initialized. Call create_db_session_factory() first.")
    return sessionFactory


async def dispose_db_engine() -> None:
    global engine
    if engine is not None:
        await engine.dispose()
        logger.info("Database connections closed successfully")
        engine = None
    else:
        logger.warning("Engine was not initialized; nothing to clean up")


def generate_ddl() -> str:
    if engine is None:
        raise ValueError("Engine is not initialized. Call create_db_engine() first.")
    from sqlalchemy.schema import CreateTable

    ddl_statements = []
    for table in Base.metadata.sorted_tables:
        ddl_statements.append(str(CreateTable(table).compile(engine.sync_engine)))
    return "\n".join(ddl_statements)


async def log_database_ddl() -> None:
    if logger.isEnabledFor(DEBUG):
        logger.debug(f"DDL: \n {generate_ddl()}")
