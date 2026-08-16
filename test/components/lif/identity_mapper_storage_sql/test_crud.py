from lif.identity_mapper_storage_sql import crud
from lif.identity_mapper_storage_sql.model import IdentityMappingModel


def _model(org="org-1", person="person-1", target_system="sys-1", person_id="ext-1"):
    model = IdentityMappingModel()
    model.lif_organization_id = org
    model.lif_organization_person_id = person
    model.target_system_id = target_system
    model.target_system_person_id_type = "School-assigned number"
    model.target_system_person_id = person_id
    return model


def test_create_and_read_by_id(session):
    created = crud.create(session, _model())
    assert created.mapping_id
    fetched = crud.read(session, created.mapping_id)
    assert fetched is not None
    assert fetched.target_system_person_id == "ext-1"


def test_read_returns_none_for_missing(session):
    assert crud.read(session, "missing") is None


def test_read_by_lif_org_and_person(session):
    crud.create(session, _model(target_system="sys-1"))
    crud.create(session, _model(target_system="sys-2"))
    crud.create(session, _model(org="org-2"))
    results = crud.read_by_lif_org_and_person(session, "org-1", "person-1")
    assert len(results) == 2
    assert {r.target_system_id for r in results} == {"sys-1", "sys-2"}


def test_delete_removes_row(session):
    model = crud.create(session, _model())
    crud.delete(session, model)
    session.flush()
    assert crud.read(session, model.mapping_id) is None
