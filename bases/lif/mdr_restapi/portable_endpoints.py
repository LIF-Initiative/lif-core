"""Export and import MDR content as portable files (issue #1408, Portability Spec §8).

Exports return the file's canonical bytes (§9), not JSON re-encoded by FastAPI, so the same rows always
export to the same bytes. Imports read the raw request body, since the parser needs the bytes as sent to
catch a byte order mark, another encoding or a repeated key (§4.2).

The converter never commits: each import is one transaction, committed here on success and rolled back on
a refusal, so a refused import writes nothing.
"""

from collections.abc import Awaitable, Callable
from typing import Any, cast

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from lif.mdr_portability import (
    CrosswalkFile,
    MappingGroupFile,
    ModelFile,
    PortabilityError,
    PortabilityErrorCode,
    PortabilityErrorGroup,
    dump_canonical,
    parse_crosswalk_file,
    parse_mapping_group_file,
    parse_model_file,
)
from lif.mdr_services import portability_converter
from lif.mdr_services.datamodel_service import get_datamodel_by_id
from lif.mdr_services.valueset_service import get_value_set_by_id
from lif.mdr_utils.database_setup import get_session
from lif.mdr_utils.logger_config import get_logger
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
logger = get_logger(__name__)

Code = PortabilityErrorCode

# Create-only refusals: the file is fine, and what it describes is already installed.
EXISTS_CODES = {Code.MODEL_EXISTS, Code.GROUP_EXISTS, Code.CROSSWALK_EXISTS}

# OpenAPI descriptions of what the schema can't show: checks on the raw bytes, rules that span elements,
# and checks against the installed rows. Codes are from the spec's §10.
# Plain text, not a link: a relative link in Swagger UI would resolve against the API host.
SPEC = "`docs/specs/mdr-portable-file-format.md`"

IMPORT_RESPONSES = """
**Responses.** 201 with the result on success. Otherwise nothing is written, and `detail` lists every
refusal as `{code, element, reason}`: 409 when each one is `MODEL_EXISTS`, `GROUP_EXISTS` or
`CROSSWALK_EXISTS` (the file is fine, and its content is already installed), and 422 for anything else.
A 409 whose `detail` is a string means a concurrent import of the same content finished first.
"""

FILE_CHECKS = """
**Checks the schema doesn't show.** The body is read as raw bytes and refused when:

- it is not UTF-8 or not JSON (`FORMAT_UNKNOWN`). A leading byte order mark is accepted.
- `Format.Type` is missing or unknown (`FORMAT_UNKNOWN`), or `Format.Version` is not 1
  (`FORMAT_VERSION_UNSUPPORTED`).
- a key appears twice in one object, or a string holds an unpaired surrogate escape such as `\\ud800`
  (`FIELD_INVALID`).
- a timestamp is not RFC 3339 with at most six fractional digits (`FIELD_INVALID`).
- a model identity field (`Name`, `Version`, `ContributorOrganization`) is missing or blank
  (`MODEL_IDENTITY_INCOMPLETE`).
- a key is unknown. The schema forbids every unknown key; these come back with their own codes: a key
  named `Id` or ending in `Id` (`ROW_ID_PRESENT`), and a deprecated key such as `Placement` or a
  model's `Type` (`DEPRECATED_FIELD`).
"""

IMPORT_MODEL_DESCRIPTION = f"""Import a model file as a new model ({SPEC} §5). Returns `{{"Id": n}}`.
{FILE_CHECKS}
**Rules across elements.**

- two entities, attributes, value sets or values share a key (`DUPLICATE_KEY`).
- a reference names no element in the file (`ELEMENT_REFERENCE_UNRESOLVED`).
- containing associations form a cycle (`ASSOCIATION_CYCLE`); a cycle must go through a reference.
- `Reference` is set on an association to an attribute (`REFERENCE_INVALID`).
- a parent has two children under one `Name` (`ASSOCIATION_NAME_TAKEN`), or two top-level entities
  share a `Name` (`TOP_LEVEL_NAME_TAKEN`).
- an attribute is in no association (`UNASSOCIATED_ATTRIBUTE`).
- `Array` is set on an entity that has a parent; set it on the entity's associations instead
  (`FIELD_INVALID`).

**Against this install.** A live model with the same `Name`, `Version` and `ContributorOrganization`
exists (`MODEL_EXISTS`). To import another version, change `Details.Version` in the file.
{IMPORT_RESPONSES}"""

IMPORT_MAPPING_GROUP_DESCRIPTION = f"""Import a mapping-group file as a new transformation group ({SPEC} §6).
Returns `{{"Id": n}}`. The group arrives inactive, and must be activated before the Translator uses it.
{FILE_CHECKS}
**Rules across mappings.**

- a rule is not JSONata (`EXPRESSION_LANGUAGE_NOT_PORTABLE`).
- a mapping has no target (`MAPPING_TARGET_MISSING`) or more than one (`MAPPING_TARGET_MULTIPLE`), or
  two mappings write one target (`MAPPING_TARGET_SHARED`).
- one mapping lists a source path twice (`DUPLICATE_KEY`).
- `Details.Version` is not dotted integers such as `1.0` (`FIELD_INVALID`).

**Against this install.**

- either model is not installed (`MODEL_MISSING`). Import the models first.
- a path doesn't resolve in its model: the first segment must be a top-level entity, each later one an
  association `Name`, and the last an attribute (`PATH_INVALID`). A segment with a numeric prefix such as
  `1:` is a legacy row ID (`ROW_ID_PRESENT`). A path through one of two roles that reach the same
  entity is refused as `PATH_INVALID` until roles can be stored apart (#1434).
- a live group with the same models and `Version` exists (`GROUP_EXISTS`). To import another version,
  change `Details.Version` in the file.
{IMPORT_RESPONSES}"""

IMPORT_CROSSWALK_DESCRIPTION = f"""Import a crosswalk file as new value mappings ({SPEC} §7). Returns
`{{"Created": n}}`, the number of value mappings created; they belong to no transformation group.
{FILE_CHECKS}
**Rules across entries.** A source value is mapped twice (`CROSSWALK_SOURCE_DUPLICATE`).

**Against this install.**

- either model is not installed (`MODEL_MISSING`). Import the models first.
- a value set, or a value an entry names, is not live in its model (`ELEMENT_REFERENCE_UNRESOLVED`).
- any live value mapping already maps the source value set to the target one (`CROSSWALK_EXISTS`). There
  is no way yet to add to or replace an existing crosswalk.
{IMPORT_RESPONSES}"""

EXPORT_REFUSALS = """
**Responses.** 200 with the file in canonical form: the same rows always export to the same bytes (§9).
404 when an Id in the request is missing or deleted. Otherwise 422, with `detail` listing every reason
the content can't be written as a portable file as `{code, element, reason}`, most often `NOT_MIGRATED`
for a model that still uses a deprecated construct, such as an overlay (§11).
"""

EXPORT_MODEL_DESCRIPTION = f"Export a model as a portable model file ({SPEC} §5).\n{EXPORT_REFUSALS}"

EXPORT_MAPPING_GROUP_DESCRIPTION = f"""Export a transformation group as a portable mapping-group file ({SPEC} §6).
Its activation is local to this install and not part of the file.
{EXPORT_REFUSALS}"""

EXPORT_CROSSWALK_DESCRIPTION = f"""Export the live value mappings from one value set to another as a portable
crosswalk file ({SPEC} §7).
{EXPORT_REFUSALS}"""


def document_file_body(file_model: type) -> dict[str, Any]:
    """The OpenAPI request body for an import: the file kind's schema, which its export registers.

    The body itself is read as raw bytes rather than parsed by FastAPI, so this only documents it.
    """
    schema = {"$ref": f"#/components/schemas/{file_model.__name__}"}
    return {"requestBody": {"required": True, "content": {"application/json": {"schema": schema}}}}


def document_file_response(file_model: type, description: str) -> dict[int | str, dict[str, Any]]:
    """The OpenAPI responses for an export, which registers the file kind's schema under its name."""
    return {200: {"model": file_model, "description": description}}


def refusal_response(group: PortabilityErrorGroup) -> JSONResponse:
    """Every refusal by code and element (§10): 409 when each one is a create-only conflict, otherwise 422."""
    # error_group builds a flat group, so every member is a PortabilityError.
    errors = cast(tuple[PortabilityError, ...], group.exceptions)
    status_code = 409 if all(error.code in EXISTS_CODES for error in errors) else 422
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": [{"code": error.code.value, "element": error.element, "reason": error.reason} for error in errors]
        },
    )


def file_response(file) -> Response:
    return Response(content=dump_canonical(file), media_type="application/json")


async def lock_crosswalk_pair(session: AsyncSession, file: CrosswalkFile) -> None:
    """Hold a lock on the crosswalk's key until the transaction ends.

    Value mappings have no unique index, so two imports of one pair could both pass CROSSWALK_EXISTS.
    With this lock the second waits for the first to commit, then sees its rows and is refused. Advisory
    locks are database-wide, so the key starts with the schema the session writes to, and imports into
    different tenants don't wait on each other.
    """
    # cspell:ignore xact hashtextextended - PostgreSQL function names
    key = f"lif-mdr-crosswalk:{file.Details.model_dump_json()}"
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(current_schema() || ':' || :key, 0))"), {"key": key}
    )


async def import_crosswalk_file(session: AsyncSession, file: CrosswalkFile) -> int:
    await lock_crosswalk_pair(session, file)
    return await portability_converter.import_crosswalk(session, file)


async def import_file(
    session: AsyncSession,
    request: Request,
    parse: Callable[[bytes], Any],
    write: Callable[[AsyncSession, Any], Awaitable[int]],
    result_key: str = "Id",
) -> JSONResponse:
    """Parse the body, write it in one transaction, and return what write returns under result_key."""
    try:
        result = await write(session, parse(await request.body()))
        await session.commit()
    except PortabilityErrorGroup as group:
        await session.rollback()
        return refusal_response(group)
    except IntegrityError:
        # A concurrent import of the same key got past the create-only check; the unique index refused it.
        await session.rollback()
        logger.exception("Portable import failed due to a database integrity error")
        return JSONResponse(
            status_code=409,
            content={"detail": "Another import of the same content finished first; nothing was written."},
        )
    return JSONResponse(status_code=201, content={result_key: result})


@router.get(
    "/models/{data_model_id}",
    responses=document_file_response(ModelFile, "The model as a portable file, in canonical form"),
    description=EXPORT_MODEL_DESCRIPTION,
)
async def export_model(data_model_id: int, session: AsyncSession = Depends(get_session)):
    # A missing or deleted model is a 404, as it is for a mapping group, not a MODEL_MISSING refusal.
    await get_datamodel_by_id(session=session, id=data_model_id)
    try:
        return file_response(await portability_converter.export_model(session, data_model_id))
    except PortabilityErrorGroup as group:
        return refusal_response(group)


@router.post(
    "/models", status_code=201, openapi_extra=document_file_body(ModelFile), description=IMPORT_MODEL_DESCRIPTION
)
async def import_model(request: Request, session: AsyncSession = Depends(get_session)):
    return await import_file(session, request, parse_model_file, portability_converter.import_model)


@router.get(
    "/mapping_groups/{group_id}",
    responses=document_file_response(MappingGroupFile, "The mapping group as a portable file, in canonical form"),
    description=EXPORT_MAPPING_GROUP_DESCRIPTION,
)
async def export_mapping_group(group_id: int, session: AsyncSession = Depends(get_session)):
    try:
        return file_response(await portability_converter.export_mapping_group(session, group_id))
    except PortabilityErrorGroup as group:
        return refusal_response(group)


@router.post(
    "/mapping_groups",
    status_code=201,
    openapi_extra=document_file_body(MappingGroupFile),
    description=IMPORT_MAPPING_GROUP_DESCRIPTION,
)
async def import_mapping_group(request: Request, session: AsyncSession = Depends(get_session)):
    return await import_file(session, request, parse_mapping_group_file, portability_converter.import_mapping_group)


@router.get(
    "/crosswalks",
    responses=document_file_response(CrosswalkFile, "The pair's value mappings as a portable file, in canonical form"),
    description=EXPORT_CROSSWALK_DESCRIPTION,
)
async def export_crosswalk(
    source_value_set_id: int, target_value_set_id: int, session: AsyncSession = Depends(get_session)
):
    # A missing or deleted value set is a 404, as a model is.
    for value_set_id in (source_value_set_id, target_value_set_id):
        await get_value_set_by_id(session=session, id=value_set_id)
    try:
        return file_response(
            await portability_converter.export_crosswalk(session, source_value_set_id, target_value_set_id)
        )
    except PortabilityErrorGroup as group:
        return refusal_response(group)


@router.post(
    "/crosswalks",
    status_code=201,
    openapi_extra=document_file_body(CrosswalkFile),
    description=IMPORT_CROSSWALK_DESCRIPTION,
)
async def import_crosswalk(request: Request, session: AsyncSession = Depends(get_session)):
    # A crosswalk is many value mapping rows, so the response is how many were created, not an Id.
    return await import_file(session, request, parse_crosswalk_file, import_crosswalk_file, result_key="Created")
