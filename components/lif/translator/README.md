# `translator` — Component

Applies JSONata-based transformations to convert data between schemas. Source schema id + target schema id + raw input → translated output. Used by the orchestrator (source-system → LIF) and the Learner Data Export service (LIF → external formats like OpenBadges 3.0 or CEDS).

## Public surface

```python
from lif.translator.core import Translator, TranslatorConfig
from lif.translator import utils
```

`TranslatorConfig(source_schema_id, target_schema_id)` describes the transformation; `Translator(config).run(input_data)` executes it. The translator fetches transformation definitions from MDR via [`mdr_client`](../mdr_client/) at run-time.

## Layout

| File | Contents |
|---|---|
| `core.py` | `Translator`, `TranslatorConfig` |
| `utils.py` | JSONata helpers + path-resolution utilities |

## Used by
- `bases/lif/translator_restapi` — single consumer; mounts `Translator` behind `POST /translate/source/{source_schema_id}/target/{target_schema_id}`
