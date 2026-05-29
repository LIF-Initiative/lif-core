# Learner Data Export API

The **Learner Data Export API** exports learner data in formats other than the Org LIF data model.

Offers two abilities:

- An endpoint to enumerate the available "Org LIF to other data models" that have a transformation group setup in **MDR**.
- An endpoint to consume a learner ID, dataModel, and transformation version. The endpoint will return data, for that learner, in that data model format
- Leverages **LIF Query Planner**, **MDR API**, and the **Translator**.


# Example usage

## Build the project
Navigate to this folder (where the `pyproject.toml` file is)

1. Export the dependencies (when using uv workspaces and having no project-specific lock-file):
``` shell
uv export --no-emit-project --output-file requirements.txt
```

2. Build a wheel:
``` shell
uv build --out-dir ./dist
```

## Build a docker image from root

``` shell
./build-docker.sh
```


## Run the image

``` shell
docker run --rm --name learner_data_export_api -p 8013:8013 \
    lif-learner-data-export-api
```

The OpenAPI specification of this FastAPI app can now be accessed at http://localhost:8013/docs#


## API Calls for Manual Testing

You can manually test the API endpoints using `curl` and an environment variable for your access token. 

*Note:* For now, the access token is a static value from the configuration.

### Health Check
```shell
curl -X GET http://localhost:8013/health-check \
  -H "Content-Type: application/json"
```

### Test Auth
```shell
curl -X GET http://localhost:8013/test/auth-info \
  -H "Content-Type: application/json" \
  -H "X-API-Key: changeme6"
```

### Get Available Data Formats
```shell
curl -X GET http://localhost:8013/available-data-formats \
  -H "Content-Type: application/json" \
  -H "X-API-Key: changeme6"
```

### Export Learner Data
```shell
curl -X GET http://localhost:8013/export \
  -H "Content-Type: application/json" \
  -H "X-API-Key: changeme6"
```
