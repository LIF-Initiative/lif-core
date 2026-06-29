"""Tests for the Cognito pre-signup Lambda (issue #917 PR 1).

The handler is defined inline in ``cloudformation/cognito-selfserve.yml`` (the
artifact CloudFormation actually deploys), so we extract that source and
exercise it directly — keeping a single source of truth rather than a copy that
can drift from the deployed code.

What matters here is the *decision* logic: a disposable domain must block the
sign-up by raising, a permanent domain must pass through, and an SSM read
problem must fail open (never block a legitimate user).
"""

import os
import sys
import types
from pathlib import Path
from unittest import mock

import pytest
import yaml

TEMPLATE = Path(__file__).resolve().parents[2] / "cloudformation" / "cognito-selfserve.yml"


class _CfnLoader(yaml.SafeLoader):
    """YAML loader that tolerates CloudFormation short tags (!Sub, !GetAtt…)."""


def _construct_cfn_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_CfnLoader.add_multi_constructor("!", _construct_cfn_tag)


def _pre_signup_source() -> str:
    template = yaml.load(TEMPLATE.read_text(), Loader=_CfnLoader)
    return template["Resources"]["PreSignUpLambda"]["Properties"]["Code"]["ZipFile"]


def _load_handler(
    *, ssm_value=None, ssm_error=None, param_not_found=False, param="/dev/mdr-pre-signup/DisposableDomains"
):
    """Exec the inline Lambda source with boto3 stubbed; return its namespace.

    ``ssm_value`` populates the parameter value; ``ssm_error`` (an exception
    instance) makes get_parameter raise it; ``param_not_found`` makes it raise
    the client's own ParameterNotFound (so the handler's targeted ``except``
    matches by class identity). Each call execs into a fresh namespace, so the
    module-level domain cache starts empty every time.
    """
    ssm_client = mock.Mock()

    class ParameterNotFound(Exception):
        pass

    ssm_client.exceptions.ParameterNotFound = ParameterNotFound
    if param_not_found:
        ssm_client.get_parameter.side_effect = ParameterNotFound()
    elif ssm_error is not None:
        ssm_client.get_parameter.side_effect = ssm_error
    else:
        ssm_client.get_parameter.return_value = {"Parameter": {"Value": ssm_value or ""}}

    # SimpleNamespace (not ModuleType) so the .client attribute is set at
    # construction — keeps the type checker happy and `import boto3` still
    # resolves it from sys.modules inside the exec'd Lambda source.
    fake_boto3 = types.SimpleNamespace(client=mock.Mock(return_value=ssm_client))

    namespace: dict = {}
    with (
        mock.patch.dict(sys.modules, {"boto3": fake_boto3}),
        mock.patch.dict(os.environ, {"DISPOSABLE_DOMAINS_SSM_PARAM": param}),
    ):
        exec(compile(_pre_signup_source(), "<pre_signup>", "exec"), namespace)
    return namespace


def _event(email: str) -> dict:
    return {"request": {"userAttributes": {"email": email}}}


def test_baseline_disposable_domain_is_rejected():
    ns = _load_handler()
    with pytest.raises(Exception, match="disposable or temporary email"):
        ns["handler"](_event("bot@mailinator.com"), None)


def test_permanent_domain_passes_through():
    ns = _load_handler()
    event = _event("real.person@unicon.net")
    assert ns["handler"](event, None) is event


def test_match_is_case_and_whitespace_insensitive():
    ns = _load_handler()
    with pytest.raises(Exception, match="disposable or temporary email"):
        ns["handler"](_event("  Bot@MailInator.COM  "), None)


def test_subdomain_of_blocked_domain_is_rejected():
    # Regression: a bare blocklist entry must also cover its subdomains,
    # otherwise x@sub.mailinator.com trivially bypasses the filter.
    ns = _load_handler()
    with pytest.raises(Exception, match="disposable or temporary email"):
        ns["handler"](_event("bot@inbox.mailinator.com"), None)
    # ...but the public suffix alone must never match a legitimate address.
    ok_event = _event("real@my-school.com")
    assert ns["handler"](ok_event, None) is ok_event


def test_trailing_dot_fqdn_is_rejected():
    # Regression: the RFC-1034 trailing-dot form must not slip past the check.
    ns = _load_handler()
    with pytest.raises(Exception, match="disposable or temporary email"):
        ns["handler"](_event("bot@mailinator.com."), None)


def test_ssm_extends_the_blocklist():
    ns = _load_handler(ssm_value="evil-spam.example, another-throwaway.test")
    with pytest.raises(Exception, match="disposable or temporary email"):
        ns["handler"](_event("x@evil-spam.example"), None)
    # baseline still applies alongside the SSM additions
    with pytest.raises(Exception, match="disposable or temporary email"):
        ns["handler"](_event("x@yopmail.com"), None)


def test_missing_ssm_param_falls_back_to_baseline():
    ns = _load_handler(param_not_found=True)
    # legitimate user still allowed, baseline still enforced
    ok_event = _event("real@unicon.net")
    assert ns["handler"](ok_event, None) is ok_event
    with pytest.raises(Exception, match="disposable or temporary email"):
        ns["handler"](_event("x@mailinator.com"), None)


def test_ssm_read_error_fails_open():
    # An unexpected SSM error must not block legitimate sign-ups.
    ns = _load_handler(ssm_error=RuntimeError("ssm throttled"))
    ok_event = _event("real@unicon.net")
    assert ns["handler"](ok_event, None) is ok_event
    # baseline list is still applied despite the read failure
    with pytest.raises(Exception, match="disposable or temporary email"):
        ns["handler"](_event("x@mailinator.com"), None)


def test_missing_email_does_not_crash():
    ns = _load_handler()
    event = {"request": {"userAttributes": {}}}
    assert ns["handler"](event, None) is event
