# `exceptions` — Component

LIF-wide exception types. Services raise these instead of bare `Exception` so HTTP bases can centralize translation to status codes via `@app.exception_handler` registrations.

## Public surface

```python
from lif.exceptions.core import (
    LIFException,
    ResourceNotFoundException,
    DataNotFoundException,
    # ...
)
```

`LIFException` is the catch-all base. Sub-types convey common semantics (not-found, data-not-found, validation failure, etc.) so handlers can map them to 404 / 422 / 500 without `isinstance` chains in business code.

## Convention

When you add a new exception type, also wire its handler in any base that should respond differently to it. The translator base is a good template — see its `@app.exception_handler` cascade in `bases/lif/translator_restapi/core.py`.

## Used by
- Every REST base — handlers convert these to HTTP responses
- Service components — raise these from business logic
