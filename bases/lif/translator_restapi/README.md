# `translator_restapi` — Base

FastAPI base for the LIF Translator: transforms data from a source schema into a target schema using transformation definitions stored in the MDR. Used by the orchestrator to convert raw source-system payloads into LIF-shaped fragments (and, in the other direction, by the Learner Data Export microservice to project LIF data into external formats).

## Endpoints
- `POST /translate/source/{source_schema_id}/target/{target_schema_id}` — body is the input payload; response is the translated output
- `GET  /health`

Plus a set of `@app.exception_handler` registrations that convert internal exceptions (`LIFException`, `ResourceNotFoundException`, `RequestValidationError`, etc.) into proper HTTP status codes with stable error envelopes.

## Composes
- `exceptions` — common LIF exception types
- `logging`
- `translator` — `TranslatorConfig`, `Translator` — the actual transformation engine

## Deployed as
`projects/lif_translator_api/`
