from datetime import date, datetime
from http import HTTPStatus
from psycopg2 import Error

from lif.mdr_utils.database_setup import get_db_connection
from lif.mdr_utils.error_handling import build_exception, generate_unique_error_id, log_error_template
from lif.mdr_utils.logger_config import get_logger


logger = get_logger(__name__)


async def run_sql(
    db_type: str,
    sql_query: str,
    filter_parameter: list[str] | None = None,
    offset: int | None = None,
    limit: int | None = None,
):
    logger.info("In run SQL method..")
    logger.info("Getting connection")
    logger.info(
        "DB Type: %s, SQL: %s, filter parameter: %s, Offset: %s, limit: %s",
        db_type,
        sql_query,
        filter_parameter,
        offset,
        limit,
    )
    # Connect to your PostgreSQL database
    connection = await get_db_connection(db_type=db_type)
    logger.info("Connection successful.")

    try:
        # Create a cursor object
        cursor = connection.cursor()
        logger.info("Getting cursor and running SQL")

        logger.info("SQL query: %s", sql_query)

        if offset is not None and "$offset" in sql_query:
            logger.info("Offset is provided")
            sql_query = sql_query.replace("$offset", str(offset)).replace("$limit", str(limit))
            logger.info("Updated sql : %s", sql_query)
        # Execute a SQL query
        if filter_parameter:
            filter_tuple = tuple(filter_parameter)
            logger.info(f"Filter in tuple: {filter_tuple}")
            cursor.execute(sql_query, filter_tuple)
        else:
            cursor.execute(sql_query)

        # Fetch all the rows
        rows = cursor.fetchall()
        logger.info(rows)

        result = []
        for row in rows:
            processed_row = {}
            for i, value in enumerate(row):
                column_name = (
                    cursor.description[i][0] if isinstance(cursor.description[i], tuple) else cursor.description[i].name
                )
                if isinstance(value, (date, datetime)):
                    logger.info(column_name)
                    processed_row[column_name] = value.isoformat()
                else:
                    processed_row[column_name] = value
            result.append(processed_row)
        return result

    except (Exception, Error) as error:
        error_id = generate_unique_error_id()
        logger.error(log_error_template(), error_id, f"Error while running the SQL: {sql_query}, Error : {error}")
        raise build_exception(error_id, f"Error while running the SQL : {error}", HTTPStatus.INTERNAL_SERVER_ERROR)
    finally:
        # Close the cursor and connection
        if connection:
            cursor.close()
            connection.close()
            logger.info("DB connection is closed")


def convert_dates(record):
    """Convert date and datetime objects to strings in a record."""
    return tuple(value.isoformat() if isinstance(value, (date, datetime)) else value for value in record)


# async def get_sql_config_data(section, key):
#     logger.info("In get data method. section :  %s, key: %s", section, key)
#     try:
#         db_sqls = load_conf_file("/usr/src/service/config_files/sql_config.yaml")
#         is_parameter_order = False
#         for sqls in db_sqls[section]:
#             if sqls["name"] == key:
#                 if "parameter_order" in sqls:
#                     is_parameter_order = True
#                 if "sqls" in sqls:
#                     if is_parameter_order:
#                         return sqls["sqls"], sqls["parameter_order"]
#                     return sqls["sqls"], None
#                 if is_parameter_order:
#                     return sqls["sql"], sqls["parameter_order"]
#                 return sqls["sql"], None

#         # In case of we do not find resource(key) into our sql_config.yaml file.
#         error_id = generate_unique_error_id()
#         logger.error(
#             log_error_template(),
#             error_id,
#             f"Could not find provided resource : {key} in sql_config.yaml",
#         )
#         raise build_exception(
#             error_id,
#             f"Could not find provided resource : {key} in sql config file",
#             HTTPStatus.BAD_REQUEST,
#         )
#     except BaseException as e:
#         error_id = generate_unique_error_id()
#         logger.error(
#             log_error_template(),
#             error_id,
#             f"Error while getting config from sql_config.yaml file. Error  : {e}",
#         )
#         raise build_exception(
#             error_id,
#             f"Error while getting SQL config. Error  : {e}",
#             HTTPStatus.INTERNAL_SERVER_ERROR,
#         )


# async def get_graphql_config_data(section, key):
#     logger.info("In get data method. section :  %s, key: %s", section, key)
#     try:
#         db_sqls = load_conf_file("/usr/src/service/config_files/sql_config.yaml")
#         for sql_config in db_sqls[section]:
#             if sql_config["name"] == key:
#                 if "filters" in sql_config:
#                     return sql_config["sql"], sql_config["filters"]
#                 return sql_config["sql"], None

#         # In case of we do not find resource(key) into our sql_config.yaml file.
#         error_id = generate_unique_error_id()
#         logger.error(
#             log_error_template(),
#             error_id,
#             f"Could not find provided resource : {key} in sql_config.yaml",
#         )
#         raise build_exception(
#             error_id,
#             f"Could not find provided resource : {key} in sql config file",
#             HTTPStatus.BAD_REQUEST,
#         )
#     except BaseException as e:
#         error_id = generate_unique_error_id()
#         logger.error(
#             log_error_template(),
#             error_id,
#             f"Error while getting config from sql_config.yaml file. Error  : {e}",
#         )
#         raise build_exception(
#             error_id,
#             f"Error while getting SQL config. Error  : {e}",
#             HTTPStatus.INTERNAL_SERVER_ERROR,
#         )
