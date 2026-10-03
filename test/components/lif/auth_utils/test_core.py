import subprocess
import sys

import pytest
from starlette.requests import Request

from lif.auth_utils import DEFAULT_PUBLIC_PATH_PREFIXES, DEFAULT_PUBLIC_PATHS, extract_bearer_token, is_public_path


def _req(authorization=None):
    headers = [] if authorization is None else [(b"authorization", authorization.encode())]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


@pytest.mark.parametrize("header", ["Bearer tok", "bearer tok", "BEARER tok", "Bearer   tok  "])
def test_extract_bearer_token_accepts_any_scheme_case(header):
    assert extract_bearer_token(_req(header)) == "tok"


@pytest.mark.parametrize("header", [None, "", "Basic tok", "Bearer", "Bearer a b", "tok"])
def test_extract_bearer_token_rejects_other_shapes(header):
    assert extract_bearer_token(_req(header)) is None


def test_is_public_path_exact_and_prefix():
    assert is_public_path("/health", DEFAULT_PUBLIC_PATHS, DEFAULT_PUBLIC_PATH_PREFIXES)
    assert is_public_path("/docs/oauth2-redirect", DEFAULT_PUBLIC_PATHS, DEFAULT_PUBLIC_PATH_PREFIXES)
    assert not is_public_path("/health-check-extra", DEFAULT_PUBLIC_PATHS, DEFAULT_PUBLIC_PATH_PREFIXES)
    assert not is_public_path("/exports", DEFAULT_PUBLIC_PATHS, DEFAULT_PUBLIC_PATH_PREFIXES)


def test_jwt_free_imports_do_not_load_pyjwt():
    # GraphQL packages auth_utils (via api_key_auth) but does not ship pyjwt, so
    # importing these must never pull in `jwt`. Subprocess: this test process has
    # jwt loaded already by other tests.
    code = "import sys, lif.auth_utils, lif.api_key_auth; assert 'jwt' not in sys.modules, 'jwt was imported'"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
