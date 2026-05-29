"""Thin wrapper around the Cognito Admin API (issue #884 Phase 3 PR 2).

The MDR API calls AdminAddUserToGroup when a registered user accepts an
invite link, so they become a member of the inviter's tenant group.
This module isolates the boto3 dependency and gives endpoint code a
small, mockable surface.

Same IAM grant pattern as the post-confirmation Lambda already in
``cloudformation/cognito-selfserve.yml``: scoped to a user pool ARN,
allowing only the actions we actually need.
"""

from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from lif.mdr_utils.logger_config import get_logger

logger = get_logger(__name__)


class CognitoAdminError(Exception):
    """Wraps boto3 client/connection errors so endpoint code can catch one type."""


class UserNotFoundError(CognitoAdminError):
    """The Cognito user identified by ``sub`` does not exist in the pool."""


class GroupNotFoundError(CognitoAdminError):
    """The Cognito group does not exist in the pool."""


@dataclass(frozen=True)
class CognitoAdminConfig:
    user_pool_id: str
    region: str


def _build_client(config: CognitoAdminConfig):
    """Construct a boto3 cognito-idp client. Separate function so tests can patch it."""
    return boto3.client("cognito-idp", region_name=config.region)


def add_user_to_group(config: CognitoAdminConfig, *, username: str, group_name: str) -> None:
    """Add a Cognito user to a group.

    ``username`` is the value Cognito identifies the user by. For pools
    configured with email as alias (our case), that's typically the user's
    ``sub`` UUID. The endpoint reads it from the JWT ``sub`` claim and
    passes it through.

    Raises:
        UserNotFoundError: ``username`` doesn't exist in the pool.
        GroupNotFoundError: ``group_name`` doesn't exist in the pool.
        CognitoAdminError: anything else (throttling, network, IAM denied).
    """
    client = _build_client(config)
    try:
        client.admin_add_user_to_group(UserPoolId=config.user_pool_id, Username=username, GroupName=group_name)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code == "UserNotFoundException":
            raise UserNotFoundError(f"User {username!r} not found in pool {config.user_pool_id}") from e
        if code == "ResourceNotFoundException":
            raise GroupNotFoundError(f"Group {group_name!r} not found in pool {config.user_pool_id}") from e
        logger.exception("AdminAddUserToGroup failed: code=%s username=%s group=%s", code, username, group_name)
        raise CognitoAdminError(f"Cognito AdminAddUserToGroup failed: {code}") from e
    except BotoCoreError as e:
        logger.exception("AdminAddUserToGroup transport error: username=%s group=%s", username, group_name)
        raise CognitoAdminError(f"Cognito transport error: {e}") from e
