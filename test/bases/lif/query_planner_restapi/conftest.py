"""Config path for the Query Planner base under test.

`lif.query_planner_restapi.core` builds its `config` singleton at import time, which
reads the information-sources YAML. Without this the first test to import the module
raises `LIFException: Information sources config file not found`, so the suite only
passed because one test happened to import it first under its own `patch.dict`, and
`pytest -k <one test>` failed. Setting it here — the same shape as the test-root
`conftest.py` — makes the import order irrelevant.
"""

import os

os.environ.setdefault(
    "LIF_QUERY_PLANNER_INFORMATION_SOURCES_CONFIG_PATH",
    os.path.join(os.path.dirname(__file__), "test_information_sources_config.yml"),
)
