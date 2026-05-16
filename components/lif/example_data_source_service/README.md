# `example_data_source_service` — Component

Sample data + business logic backing the [`example_data_source_rest_api`](../../../bases/lif/example_data_source_rest_api/) base. Provides a small fake person/course dataset that adapters can exercise locally without standing up a real SIS or LMS.

## Public surface

```python
from lif.example_data_source_service.core import (
    user_info, users_info, users_info_filtered, courses_info,
)
```

| Function | Returns |
|---|---|
| `user_info(user_id)` | One sample person |
| `users_info()` | All sample persons |
| `users_info_filtered(filter)` | Subset matching the filter |
| `courses_info()` | Sample courses dataset |

## Used by
- `bases/lif/example_data_source_rest_api` — only consumer; this component exists to keep that base small and stub-able.
