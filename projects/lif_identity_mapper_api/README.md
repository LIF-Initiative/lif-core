# LIF Identity Mapper API

The **Identity Mapper API** facilitates the resolution of person identifiers from external partner organizations to the internal identifiers utilized within the organization. It enables cross-organizational sharing of LIF records for individuals using the respective identifiers from each organization.  The API provides simple CRUD operations for managing the mappings.

# Example Usage

## Build the project

Navigate to this folder (where the `pyproject.toml` file is)

``` shell
./build.sh

```

## Build a docker image from root

``` shell
./build-docker.sh
```

## Run the image

``` shell
docker run --rm --name lif_identity_mapper_api -p 8006:8006 lif-identity-mapper-api
```

The OpenAPI specification of this FastAPI app can now be accessed at http://localhost:8006/docs#

# Example API Usage

## List

GET http://localhost:8006/organizations/Org1/persons/100075/mappings/

## Save

POST http://localhost:8006/organizations/Org1/persons/100075/mappings/
with body:
```json
[
  {
    "lif_organization_id": "Org1",
    "lif_organization_person_id": "100075",
    "target_system_id": "Org2",
    "target_system_person_id_type": "SCHOOL_ASSIGNED_NUMBER",
    "target_system_person_id": "1234567"
  }
]
```

## Delete

DELETE http://localhost:8006/organizations/Org1/persons/100075/mappings/84d1f9c8-8cc8-11f0-976c-06ae7a452344
