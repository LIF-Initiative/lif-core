import pytest

from lif.mdr_portability.errors import PortabilityError, PortabilityErrorCode
from lif.mdr_portability.mapping_paths import (
    AssociationEnd,
    ModelPaths,
    ResolvedPath,
    check_path_syntax,
    to_entity_id_path,
    to_file_path,
)

Code = PortabilityErrorCode
ELEMENT = "Mappings[x].Target.Path"

# Course (1) holds two roles of Organization (2), AccreditedBy and ApprovedBy, and an attribute title
# (11). Organization holds name (12). Person (3) contains Contact (4), which contains city (13).
# Student (5) references Course; Course is the child of nothing that contains it, so it is top-level.
COURSE, ORGANIZATION, PERSON, CONTACT, STUDENT = 1, 2, 3, 4, 5
TITLE, NAME, CITY, UNNAMED = 11, 12, 13, 14


def _model(**overrides) -> ModelPaths:
    fields = dict(
        entity_names={
            COURSE: "Course",
            ORGANIZATION: "Organization",
            PERSON: "Person",
            CONTACT: "Contact",
            STUDENT: "Student",
        },
        attribute_names={TITLE: "title", NAME: "name", CITY: "city", UNNAMED: "code"},
        top_level_entity_ids=frozenset({COURSE, PERSON, STUDENT}),
        associations={
            COURSE: [
                AssociationEnd("AccreditedBy", ORGANIZATION, False),
                AssociationEnd("ApprovedBy", ORGANIZATION, False),
                AssociationEnd("title", TITLE, True),
            ],
            ORGANIZATION: [AssociationEnd("name", NAME, True)],
            PERSON: [AssociationEnd("Contact", CONTACT, False)],
            CONTACT: [AssociationEnd("city", CITY, True)],
            STUDENT: [AssociationEnd("RefCourse", COURSE, False), AssociationEnd(None, UNNAMED, True)],
        },
    )
    return ModelPaths(**(fields | overrides))


def _refusal(call) -> tuple[PortabilityErrorCode, str, str]:
    with pytest.raises(PortabilityError) as exc_info:
        call()
    return exc_info.value.code, exc_info.value.element, exc_info.value.reason


@pytest.mark.parametrize(
    "path, resolved",
    [
        ("Course,title", ResolvedPath("1,-11", COURSE, TITLE)),
        ("Person,Contact,city", ResolvedPath("3,4,-13", CONTACT, CITY)),
        ("Student,RefCourse,title", ResolvedPath("5,1,-11", COURSE, TITLE)),
    ],
)
def test_to_entity_id_path_resolves_each_segment_by_association_name(path, resolved):
    assert to_entity_id_path(path, _model(), ELEMENT) == resolved


@pytest.mark.parametrize(
    "path", ["Course,AccreditedBy,name", "Course,ApprovedBy,name", "Student,RefCourse,AccreditedBy,name"]
)
def test_to_entity_id_path_refuses_a_role_an_entity_id_path_cannot_tell_apart(path):
    # Both roles would store 1,2,-12, which export refuses, so the file could not round-trip. Import
    # refuses them too until a stored path can tell roles apart.
    code, element, reason = _refusal(lambda: to_entity_id_path(path, _model(), ELEMENT))
    assert (code, element) == (Code.PATH_INVALID, ELEMENT)
    assert "'Course' reaches 'Organization' by 2 associations ('AccreditedBy', 'ApprovedBy')" in reason


@pytest.mark.parametrize(
    "entity_id_path, path",
    [("1,-11", "Course,title"), ("3,4,-13", "Person,Contact,city"), ("5,1,-11", "Student,RefCourse,title")],
)
def test_to_file_path_names_each_step_by_its_association(entity_id_path, path):
    assert to_file_path(entity_id_path, _model(), ELEMENT) == path


def test_to_file_path_refuses_two_roles_an_entity_id_path_cannot_tell_apart():
    # 1,2,-12 is Course,AccreditedBy,name or Course,ApprovedBy,name: export must not pick one.
    code, element, reason = _refusal(lambda: to_file_path("1,2,-12", _model(), ELEMENT))
    assert (code, element) == (Code.PATH_INVALID, ELEMENT)
    assert "'AccreditedBy', 'ApprovedBy'" in reason


@pytest.mark.parametrize(
    "entity_id_path, reason_part",
    [
        ("1,x,-11", "not a list of IDs"),
        ("1,11", "not entities followed by one attribute"),  # no attribute at the end
        ("-11", "not entities followed by one attribute"),  # an attribute alone
        ("1,-2,-12", "not entities followed by one attribute"),  # an attribute mid-path
        ("99,-11", "not a live entity"),
        ("4,-13", "not a top-level entity"),  # Contact is contained by Person
        ("1,4,-13", "no live association leads from 'Course' to 'Contact'"),
        ("1,-13", "no live association leads from 'Course' to 'city'"),
        ("5,-14", "has no Name yet"),  # an association created before its Name was written
    ],
)
def test_to_file_path_refuses_a_stored_path_it_cannot_name(entity_id_path, reason_part):
    code, element, reason = _refusal(lambda: to_file_path(entity_id_path, _model(), ELEMENT))
    assert (code, element) == (Code.PATH_INVALID, ELEMENT)
    assert reason_part in reason


@pytest.mark.parametrize(
    "path, reason_part",
    [
        ("Organization,name", "no top-level entity has the UniqueName 'Organization'"),  # contained only
        ("Contact,city", "no top-level entity has the UniqueName 'Contact'"),
        ("Course,AwardedBy,name", "'Course' has no association named 'AwardedBy'"),
        ("Course,AccreditedBy", "'AccreditedBy' is an entity; a path ends at an attribute"),
        ("Course,title,name", "'title' is an attribute, so it must be last"),
    ],
)
def test_to_entity_id_path_refuses_a_path_the_model_does_not_have(path, reason_part):
    code, element, reason = _refusal(lambda: to_entity_id_path(path, _model(), ELEMENT))
    assert (code, element) == (Code.PATH_INVALID, ELEMENT)
    assert reason_part in reason


def test_to_entity_id_path_refuses_a_name_two_associations_share():
    # The database has no unique index on (parent, Name): flattening model 17 makes two (#1388).
    associations = _model().associations | {
        COURSE: [AssociationEnd("Sponsor", ORGANIZATION, False), AssociationEnd("Sponsor", PERSON, False)]
    }
    code, _, reason = _refusal(
        lambda: to_entity_id_path("Course,Sponsor,name", _model(associations=associations), ELEMENT)
    )
    assert code == Code.PATH_INVALID
    assert "'Course' has 2 associations named 'Sponsor'" in reason


@pytest.mark.parametrize(
    "path, codes",
    [
        ("Course,title", []),
        ("1:Assessment,1:~Assessment.identifier", [Code.ROW_ID_PRESENT, Code.ROW_ID_PRESENT]),
        ("Course", [Code.PATH_INVALID]),
        ("Course,,title", [Code.PATH_INVALID]),
        ("", [Code.PATH_INVALID]),
        (" ,title", [Code.PATH_INVALID]),
    ],
)
def test_check_path_syntax(path, codes):
    assert [error.code for error in check_path_syntax(path, ELEMENT)] == codes


def test_row_id_segment_is_named_in_the_reason():
    # Portability Spec §12.3: ROW_ID_PRESENT names the segment `1:Assessment`.
    errors = check_path_syntax("1:Assessment,identifier", ELEMENT)
    assert [(error.code, error.element) for error in errors] == [(Code.ROW_ID_PRESENT, ELEMENT)]
    assert "'1:Assessment'" in errors[0].reason


def test_to_entity_id_path_checks_syntax_first():
    code, _, _ = _refusal(lambda: to_entity_id_path("1:Course,title", _model(), ELEMENT))
    assert code == Code.ROW_ID_PRESENT


@pytest.mark.parametrize("path", ["Course,title", "Person,Contact,city", "Student,RefCourse,title"])
def test_a_resolved_path_names_back_to_itself(path):
    model = _model()
    assert to_file_path(to_entity_id_path(path, model, ELEMENT).entity_id_path, model, ELEMENT) == path
