import os

# The LDE app wires the api_key_auth middleware at import time from LDE_AUTH__API_KEYS,
# and auth self-disables when no keys are configured. Set a known test key here —
# before test_core.py imports lif.learner_data_export_api.core — so auth is enabled
# and the suite can exercise the 401 / valid-key paths deterministically.
os.environ.setdefault("LDE_AUTH__API_KEYS", "test-lde-key:test-client")
