"""
LIF Query Cache Service

This component provides a service that accepts LIF queries and LIF updates,
converts them to datastore-specific queries/updates, and returns results from
the 'person' collection. It includes utilities for field projection cleanup
and filter conversion.
"""

from typing import Any, Dict, List

from pymongo.asynchronous.database import AsyncDatabase

from lif.composer.core import compose_with_fragment_list
from lif.datatypes.core import (
    LIFFragment,
    LIFQuery,
    LIFQueryFilter,
    LIFPersonIdentifiers,
    LIFPerson,
    LIFRecord,
    LIFUpdate,
)
from lif.exceptions.core import ResourceNotFoundException
from lif.logging.core import get_logger
from lif.mongodb_connection.core import get_database_async

logger = get_logger(__name__)

# -------------------------------------------------------------------------
# MongoDB Connection (ASYNC)
# -------------------------------------------------------------------------
db: AsyncDatabase = get_database_async("LIF")
collection = db["person"]


# -------------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------------
def clean_projection(selected_fields: List[str], keep: str = "branches") -> List[str]:
    """
    Removes redundant nested fields from projection list.
    If keep == "branches", keep highest level paths (parents over children).
    If keep == "leaves", keep only leaves (children over parents).

    NOTE: Added 'branches' and 'leaves' to be able to test broader return values
          of branches when testing for types and dict to class conversions

    """
    fields_set = set(selected_fields)
    result = set()

    if keep == "branches":
        # Favor higher branches
        for field in sorted(fields_set, key=lambda x: x.count(".")):
            parts = field.split(".")
            for i in range(1, len(parts)):
                parent = ".".join(parts[:i])
                if parent in fields_set:
                    break
            else:
                result.add(field)

    elif keep == "leaves":
        # Favor leaves (deepest fields)
        for field in sorted(fields_set, key=lambda x: -x.count(".")):
            if not any(other != field and other.startswith(field + ".") for other in fields_set):
                result.add(field)
    else:
        raise ValueError("keep must be 'branches' or 'leaves'")

    return list(result)


def extract_filter(filter_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Converts nested filter dicts into Mongo dot notation filters."""
    mongo_filter = {}
    for key, value in filter_dict.items():
        if isinstance(value, dict):
            nested = extract_filter(value)
            for subkey, subval in nested.items():
                mongo_filter[f"{key}.{subkey}"] = subval
        elif isinstance(value, list):
            if len(value) == 1 and isinstance(value[0], dict):
                mongo_filter[key] = {"$elemMatch": extract_filter(value[0])}
            elif all(isinstance(item, dict) for item in value):
                mongo_filter[key] = {"$elemMatch": {"$or": [extract_filter(v) for v in value]}}
            else:
                mongo_filter[key] = {"$in": value}
        else:
            mongo_filter[key] = value
    return mongo_filter


def build_mongo_update_ops(update_fields, root_prefix="person.0"):
    """Recursively builds $set and $push update dicts for MongoDB."""
    set_ops = {}
    push_ops = {}
    for k, v in update_fields.items():
        key_path = f"{root_prefix}.{k}"
        if isinstance(v, dict):
            sub_set, sub_push = build_mongo_update_ops(v, key_path)
            set_ops.update(sub_set)
            push_ops.update(sub_push)
        elif isinstance(v, list):
            push_ops.setdefault(key_path, []).extend(v)
        else:
            set_ops[key_path] = v
    return set_ops, push_ops


def format_push_ops(push_ops):
    """Formats push operations to use $each when needed."""
    formatted = {}
    for k, v in push_ops.items():
        if len(v) > 1:
            formatted[k] = {"$each": v}
        elif len(v) == 1:
            formatted[k] = v[0]
    return formatted


def extract_updated_fields(update_fields):
    """Builds a shallow dict containing only the updated fields (top-level keys)."""
    result = {}
    for k, v in update_fields.items():
        if isinstance(v, list) and len(v) == 1:
            # If a single object pushed, return the object, not a list
            result[k] = v[0]
        else:
            result[k] = v
    return result


# -------------------------------------------------------------------------
# Main function to run a query (ASYNC)
# -------------------------------------------------------------------------
async def query(query: LIFQuery) -> List[LIFRecord]:
    """
    Executes a query on the MongoDB 'person' collection, supporting nested filters and custom projections.

    Args:
        query (LIFQuery): Input query with filter and selected fields.

    Returns:
        List[Any]: List of matching documents with only the requested fields.

    Raises:
        Exception: If the query fails.
    """
    try:
        cleaned_fields = clean_projection(query.selected_fields, keep="leaves")
        mongo_filter = extract_filter(query.filter.model_dump())
        mongo_projection = {field: 1 for field in cleaned_fields}
        mongo_projection["_id"] = 0

        logger.info("===> WILL NOW MAKE MONGODB COLLECTION.FIND CALL:")
        logger.info(f"FILTER: {mongo_filter}")
        logger.info(f"PROJECTION: {mongo_projection}")
        cursor = collection.find(mongo_filter, mongo_projection)
        logger.info("===> DONE MAKING MONGODB CALL")
        results = []
        async for doc in cursor:
            results.append(doc)

        logger.info("===> DONE COLLECTING RESULTS FROM MONGODB CALL")
        logger.info("===> QUERY CACHE RETURNING: " + str(results))
        return results
    except Exception as e:
        logger.exception("Query Exception: %s", e)
        raise


# -------------------------------------------------------------------------
# Main function to run an update (ASYNC)
# -------------------------------------------------------------------------
async def update(lif_update: LIFUpdate) -> LIFRecord:
    """
    Execute a LIF Update on the MongoDB 'person' collection.
    Updates fields in 'person[0]' of a MongoDB document and returns the updated person array.

    Args:
        update (LIFUpdate): Input model containing filter and update fields.

    Returns:
        LIFRecord: The updated 'person' array (without '_id').

    Raises:
        Exception: If the update fails.
    """
    try:
        logger.info(f"===> CALL MADE TO UPDATE: {lif_update}")
        filter_dict = lif_update.updatePerson.filter
        update_fields = lif_update.updatePerson.input

        # Unwrap "person" key if present
        if "person" in update_fields and isinstance(update_fields["person"], dict):
            update_fields = update_fields["person"]

        mongo_filter = extract_filter(filter_dict) if filter_dict else {}

        set_ops, push_ops = build_mongo_update_ops(update_fields, "person.0")
        update_doc = {}

        # --- Step 1: Ensure all $push targets are arrays, using $set in a SEPARATE update ---
        array_inits = {}
        if push_ops:
            current_doc = await collection.find_one(mongo_filter, {"person": 1})
            for field_path in push_ops:
                keys = field_path.split(".")
                val = current_doc
                try:
                    for k in keys:
                        if isinstance(val, list) and k.isdigit():
                            idx = int(k)
                            val = val[idx] if len(val) > idx else None
                        elif isinstance(val, dict):
                            val = val.get(k)
                        else:
                            val = None
                    if val is None or not isinstance(val, list):
                        array_inits[field_path] = []
                except Exception:
                    array_inits[field_path] = []
        if array_inits:
            # FIRST update: just $set any array initializations (NO $push here)
            await collection.update_one(mongo_filter, {"$set": array_inits})

        # --- Step 2: Main update ---
        if set_ops:
            update_doc["$set"] = set_ops
        if push_ops:
            formatted_push = format_push_ops(push_ops)
            if formatted_push:
                update_doc["$push"] = formatted_push

        if not update_doc:
            raise ValueError("No update fields provided.")

        logger.info("===> WILL NOW MAKE MONGODB COLLECTION.UPDATE_ONE CALL: ")
        logger.info(f"FILTER: {mongo_filter}")
        logger.info(f"UPDATE DOC: {update_doc}")
        await collection.update_one(mongo_filter, update_doc)
        logger.info("===> DONE MAKING MONGODB CALL")

        # Return ONLY the full 'person' array as { "person": [ ... ] }
        doc = await collection.find_one(mongo_filter, {"person": 1, "_id": 0})
        if doc and "person" in doc:
            return LIFRecord(person=doc["person"])
        raise ResourceNotFoundException(resource_id=None, message=f"No matching record after update: {filter_dict}")

    except Exception as e:
        logger.exception("Update Exception: %s", e)
        raise


# -------------------------------------------------------------------------
# Main function to run an add (ASYNC)
# -------------------------------------------------------------------------
async def add(lif_record: LIFRecord) -> LIFRecord:
    """
    Adds a new LIFRecord to the MongoDB 'person' collection.

    Args:
        lif_record (LIFRecord): The record to add.

    Returns:
        LIFRecord: The added record with '_id' field included.

    Raises:
        Exception: If the add operation fails.
    """
    try:
        logger.info(f"===> CALL MADE TO ADD: {lif_record}")
        result = await collection.insert_one(lif_record.model_dump())
        if result.inserted_id:
            added_record = await collection.find_one({"_id": result.inserted_id})
            return LIFRecord(**added_record)  # type: ignore
        raise ResourceNotFoundException("Failed to add record, no inserted ID returned.")
    except Exception as e:
        logger.exception("Add Exception: %s", e)
        raise


async def save(lif_query_filter: LIFQueryFilter, lif_fragments: List[LIFFragment]):
    """
    Uses the LIFQueryFilter to find a LIFRecord in the 'person' collection.
    If found, it updates the LIFRecord with the data from the LIFFragment list.
    If no LIFRecord is found, it creates a new one with the data from the LIFFragment list.

    Args:
        lif_query_filter (LIFQueryFilter): The filter to find the LIFRecord to update.
        lif_fragments (List[LIFFragment]): The fragments to save.

    Raises:
        Exception: If the save operation fails or if the LIFQueryFilter results in more than one LIFRecord being found.
    """
    try:
        mongo_filter = extract_filter(lif_query_filter.model_dump())
        cursor = collection.find(mongo_filter)
        results = []
        async for doc in cursor:
            results.append(doc)
        if len(results) > 1:
            raise ValueError(f"Cannot save -- multiple records found for the given filter: {lif_query_filter}")

        person_identifiers: LIFPersonIdentifiers = LIFPersonIdentifiers(
            identifier=lif_query_filter.root.person.identifier
        )
        lif_person: LIFPerson = LIFPerson(root=[person_identifiers.model_dump()])
        lif_record = LIFRecord(**results[0]) if len(results) == 1 else LIFRecord(person=lif_person)

        updated_lif_record = compose_with_fragment_list(lif_record, lif_fragments)
        mongo_update_response = await collection.update_one(
            mongo_filter, {"$set": updated_lif_record.model_dump()}, upsert=True
        )
        logger.debug(f"MONGO UPDATE RESPONSE: {mongo_update_response}")
    except Exception as e:
        logger.exception("Save Exception: %s", e)
        raise
