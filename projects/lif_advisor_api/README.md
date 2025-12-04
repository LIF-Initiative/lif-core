# Advisor AI

The **Advisor API** facilitates a conversational experience by authenticating users, managing session states,
and interacting with a language model agent to provide personalized chat interactions using the user's LIF data as context.

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

## Export environment variables
``` shell
export OPENAI_API_KEY=sk-proj-xxx  # insert your own key
```

## Run the image

``` shell
docker run --rm --name lif_advisor_api -p 8004:8004 \
    -e LIF_SEMANTIC_SEARCH_MCP_SERVER_URL=http://host.docker.internal:8003/mcp \
    -e LIF_GRAPHQL_API_URL=http://host.docker.internal:8002/graphql \
    -e LANGCHAIN_LLM_MODEL_NAME=gpt-4.1-mini \
    -e OPENAI_API_KEY=$OPENAI_API_KEY \
    lif-advisor-api
````

The OpenAPI specification of this FastAPI app can now be accessed at http://localhost:8004/docs#


## API Calls for Manual Testing

You can manually test the API endpoints using `curl` and an environment variable for your access token. 

> **Important:** Some of these require an `OPENAI_API_KEY` and will incur cost to run.

### Login (get your access token)
```shell
curl -X POST http://localhost:8004/login \
  -H "Content-Type: application/json" \
  -d '{"username":"atsatrian_lifdemo@stateu.edu","password":"password"}'
```

This will return a JSON response with an `access_token` and `refresh_token`. Copy the `access_token` and export it as an environment variable:

```shell
export ACCESS_TOKEN="<your-access-token>"
```

Replace `<your-access-token>` with the value you received from the login endpoint or your test token.

### Get initial message
```shell
curl -X GET http://localhost:8004/initial-message \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

### Start conversation
```shell
curl -X POST http://localhost:8004/start-conversation \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

### Continue conversation
```shell
curl -X POST http://localhost:8004/continue-conversation \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"What are my strengths?"}'
```

### Logout
```shell
curl -X POST http://localhost:8004/logout \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

You can repeat the continue conversation step with different messages to interact with the advisor agent.
