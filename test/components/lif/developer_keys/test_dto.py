"""The pydantic v2 config of DeveloperApiKeyDTO (#1467).

Both key listings build the DTO from ORM rows with ``model_validate``, so ``from_attributes`` must
stay on. The v1-style ``orm_mode`` it replaced only raised a ``UserWarning`` on import.
"""

import subprocess
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

from lif.developer_keys import DeveloperApiKeyDTO


def test_dto_validates_from_an_orm_row():
    row = SimpleNamespace(
        Id=7,
        Label="my app",
        KeyPrefix="lifk_abcdefg",
        CreationDate=datetime(2026, 11, 4, tzinfo=timezone.utc),
        LastUsedDate=None,
        RevokedDate=None,
    )

    dto = DeveloperApiKeyDTO.model_validate(row)

    assert dto.Id == 7
    assert dto.KeyPrefix == "lifk_abcdefg"


def test_dto_module_imports_without_a_config_warning():
    # A fresh interpreter, because the module is already imported (and its warning already
    # emitted) in this one.
    result = subprocess.run(
        [sys.executable, "-W", "error::UserWarning", "-c", "import lif.developer_keys.dto"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
