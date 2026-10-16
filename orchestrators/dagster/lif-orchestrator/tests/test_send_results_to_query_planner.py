"""The results callback's X-API-Key header (#1108).

An SSM value with a trailing newline (the #1115 trap) makes `requests` raise before sending, which
would fail every orchestrated run even against a planner that enforces no keys.
"""

from unittest import mock

import dagster as dg

# The repo-root ty run can't see this project's src/; pytest finds it through pythonpath in pyproject.toml.
from lif_orchestrator.defs import lif_job  # ty: ignore[unresolved-import]


def _send_results(env: dict[str, str]) -> dict[str, str]:
    """Run the op with no plan parts and return the headers it POSTed with."""
    with mock.patch.dict("os.environ", env), mock.patch.object(lif_job.requests, "post") as post:
        lif_job.send_results_to_query_planner(
            context=dg.build_op_context(), config_resource=lif_job.SharedOpConfig(), results=[]
        )
    return post.call_args.kwargs["headers"]


def test_sends_the_key_stripped_of_surrounding_whitespace():
    headers = _send_results({"LIF_QUERY_PLANNER_API_KEY": " qp-key\n"})

    assert headers["X-API-Key"] == "qp-key"


def test_sends_no_key_header_when_the_key_is_unset_or_blank():
    headers = _send_results({"LIF_QUERY_PLANNER_API_KEY": "\n"})

    assert "X-API-Key" not in headers
