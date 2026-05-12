"""Unit tests for the cognito_admin boto3 wrapper.

The real boto3 client is patched out; these tests confirm the wrapper
translates Cognito error codes into the right exception types so the
endpoint layer can react appropriately.
"""

from unittest import mock

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from lif.mdr_auth.cognito_admin import (
    CognitoAdminConfig,
    CognitoAdminError,
    GroupNotFoundError,
    UserNotFoundError,
    add_user_to_group,
)

CONFIG = CognitoAdminConfig(user_pool_id="us-east-1_TestPool", region="us-east-1")


@pytest.fixture
def mock_client(monkeypatch):
    """Patch boto3 client construction so no real AWS calls leak through."""
    import lif.mdr_auth.cognito_admin as mod

    client = mock.MagicMock()
    monkeypatch.setattr(mod, "_build_client", lambda config: client)
    return client


class TestAddUserToGroup:
    def test_happy_path_calls_admin_add_user_to_group(self, mock_client):
        add_user_to_group(CONFIG, username="sub-123", group_name="lif-team")
        mock_client.admin_add_user_to_group.assert_called_once_with(
            UserPoolId="us-east-1_TestPool", Username="sub-123", GroupName="lif-team"
        )

    def test_user_not_found_raises_typed_error(self, mock_client):
        mock_client.admin_add_user_to_group.side_effect = ClientError(
            {"Error": {"Code": "UserNotFoundException", "Message": "User not found"}}, "AdminAddUserToGroup"
        )
        with pytest.raises(UserNotFoundError):
            add_user_to_group(CONFIG, username="sub-123", group_name="lif-team")

    def test_group_not_found_raises_typed_error(self, mock_client):
        """Cognito returns ResourceNotFoundException when the group doesn't exist;
        we translate to GroupNotFoundError so the endpoint can distinguish from
        the user-not-found case."""
        mock_client.admin_add_user_to_group.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Group not found"}}, "AdminAddUserToGroup"
        )
        with pytest.raises(GroupNotFoundError):
            add_user_to_group(CONFIG, username="sub-123", group_name="lif-team")

    def test_other_client_error_raises_generic_admin_error(self, mock_client):
        """Throttling, internal-error, etc. surface as the generic CognitoAdminError
        so endpoints don't have to enumerate every possible failure code."""
        mock_client.admin_add_user_to_group.side_effect = ClientError(
            {"Error": {"Code": "TooManyRequestsException", "Message": "Rate exceeded"}}, "AdminAddUserToGroup"
        )
        with pytest.raises(CognitoAdminError) as exc_info:
            add_user_to_group(CONFIG, username="sub-123", group_name="lif-team")
        assert "TooManyRequestsException" in str(exc_info.value)
        # Confirm it's *not* one of the specific subclasses
        assert not isinstance(exc_info.value, (UserNotFoundError, GroupNotFoundError))

    def test_botocore_transport_error_raises_admin_error(self, mock_client):
        mock_client.admin_add_user_to_group.side_effect = BotoCoreError()
        with pytest.raises(CognitoAdminError):
            add_user_to_group(CONFIG, username="sub-123", group_name="lif-team")
