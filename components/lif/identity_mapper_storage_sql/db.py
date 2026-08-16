from logging import DEBUG
from os import getenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import declarative_base, sessionmaker, Session

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
db_pool_pre_ping: bool = getenv("IDENTITY_MAPPER_DB_POOL_PRE_PING", "false").lower() == "true"


logger = get_logger(__name__)
engine: Engine | None = None
sessionFactory: sessionmaker[Session] | None = None
Base = declarative_base()


def validate_db_environment() -> None:
    if not db_driver_name or not db_username or not db_password or not db_host:
        raise ValueError("Database configuration environment variables are not set properly")


def create_db_connection_url() -> URL:
    return URL.create(
        drivername=db_driver_name if db_driver_name else "",
        username=db_username,
        password=db_password,
        host=db_host,
        port=int(db_port),
        database=db_name,
    )


def create_db_engine():
    validate_db_environment()
    url: URL = create_db_connection_url()
    global engine
    engine = create_engine(
        url, connect_args=db_connect_args or {}, pool_size=db_pool_size, pool_pre_ping=db_pool_pre_ping
    )


def create_db_session_factory():
    global sessionFactory
    if engine is None:
        raise ValueError("Engine is not initialized. Call create_db_engine() first.")
    sessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def initialize_database() -> None:
    create_db_engine()
    create_db_session_factory()
    log_database_ddl()
    if db_auto_create_tables:
        Base.metadata.create_all(engine)
        logger.info("Database tables created successfully")


def get_db_session_factory() -> sessionmaker[Session]:
    if sessionFactory is None:
        raise ValueError("Session Factory is not initialized. Call create_db_session_factory() first.")
    return sessionFactory


def dispose_db_engine() -> None:
    global engine
    if engine is not None:
        engine.dispose()
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
        ddl_statements.append(str(CreateTable(table).compile(engine)))
    return "\n".join(ddl_statements)


def log_database_ddl() -> None:
    if logger.isEnabledFor(DEBUG):
        logger.debug(f"DDL: \n {generate_ddl()}")
