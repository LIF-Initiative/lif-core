from unittest.mock import AsyncMock, patch

import pytest
from deepdiff import DeepDiff
from httpx import ASGITransport, AsyncClient
from lif.advisor_restapi import core
from lif.langchain_agent.core import LIFAIAgent

from test.utils.lif.advisor.auth import login_user_to_lif_advisor, logout_user_from_lif_advisor


def get_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=core.app), base_url="http://test")


# This mock will eventually be built out more.
class MockAgent:
    def __init__(self):
        self.ask_agent = AsyncMock(return_value={"content": "This is mocked content", "tokens": 10, "cost": 0.57})


# From the hard coded users in lif/advisor_restapi
USER_DETAILS_ALEX = {"username": "atsatrian_lifdemo@stateu.edu", "password": "changeme"}


@pytest.mark.asyncio
async def test_login_successful():
    mocked_ai_agent = MockAgent()

    async with get_client() as client:
        with patch.object(LIFAIAgent, "setup", new=AsyncMock(return_value=mocked_ai_agent)) as setup_mock:
            # Test /login

            expected_response = {
                "success": True,
                "message": "Login successful",
                "user": {
                    "username": "atsatrian_lifdemo@stateu.edu",
                    "firstname": "Alan",
                    # cspell:ignore Tsatrian
                    "lastname": "Tsatrian",
                    "identifier": "100001",
                    "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
                    "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
                },
                "access_token": "",  # will be replaced in the login function
                "refresh_token": "",  # will be replaced in the login function
            }
            await login_user_to_lif_advisor(
                client=client,
                username=USER_DETAILS_ALEX["username"],
                password=USER_DETAILS_ALEX["password"],
                expected_response=expected_response,
            )

            # Verify the calls to the LIFAIAgent

            setup_mock.assert_awaited_once()
            mocked_ai_agent.ask_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_login_user_not_found():
    details = {"username": "does_not_exist", "password": "asdf"}
    async with get_client() as client:
        response = await client.post("/login", json=details)
        assert response.status_code == 401
        response_json = response.json()
        expected_response = {"detail": "Invalid credentials"}
        diff = DeepDiff(expected_response, response_json)
        assert not diff, diff  # prints out the differences if any


@pytest.mark.asyncio
async def test_login_wrong_password():
    details = {"username": "atsatrian_lifdemo@stateu.edu", "password": "wrong_password"}
    async with get_client() as client:
        response = await client.post("/login", json=details)
        assert response.status_code == 401
        response_json = response.json()
        expected_response = {"detail": "Invalid credentials"}
        diff = DeepDiff(expected_response, response_json)
        assert not diff, diff  # prints out the differences if any


@pytest.mark.asyncio
async def test_refresh_token_success():
    mocked_ai_agent = MockAgent()

    async with get_client() as client:
        with patch.object(LIFAIAgent, "setup", new=AsyncMock(return_value=mocked_ai_agent)):
            # Login to gather a refresh token

            login_response_json = await login_user_to_lif_advisor(
                client=client, username=USER_DETAILS_ALEX["username"], password=USER_DETAILS_ALEX["password"]
            )
            response_access_token = login_response_json.get("access_token", None)
            assert response_access_token is not None, "No access token in login response"
            response_refresh_token = login_response_json.get("refresh_token", None)
            assert response_refresh_token is not None, "No refresh token in login response"

            # Refresh the token

            auth_headers = {"Authorization": f"Bearer {response_access_token}"}
            refresh_token_response = await client.post(
                "/refresh-token", json={"refresh_token": response_refresh_token}, headers=auth_headers
            )
            assert refresh_token_response.status_code == 200
            refresh_token_response_json = refresh_token_response.json()
            refresh_token_expected_response = {"access_token": refresh_token_response_json.get("access_token")}
            refresh_token_diff = DeepDiff(refresh_token_expected_response, refresh_token_response_json)
            assert not refresh_token_diff, refresh_token_diff  # prints out the differences if any


@pytest.mark.asyncio
async def test_refresh_token_invalid_refresh_token():
    mocked_ai_agent = MockAgent()

    async with get_client() as client:
        with patch.object(LIFAIAgent, "setup", new=AsyncMock(return_value=mocked_ai_agent)):
            # Login to gather an access token

            login_response_json = await login_user_to_lif_advisor(
                client=client, username=USER_DETAILS_ALEX["username"], password=USER_DETAILS_ALEX["password"]
            )
            response_access_token = login_response_json.get("access_token", None)
            assert response_access_token is not None, "No access token in login response"

            # Refresh the token with an invalid refresh token

            auth_headers = {"Authorization": f"Bearer {response_access_token}"}
            refresh_token_response = await client.post(
                "/refresh-token", json={"refresh_token": "eyASDFqr"}, headers=auth_headers
            )
            assert refresh_token_response.status_code == 401
            refresh_token_response_json = refresh_token_response.json()
            refresh_token_expected_response = {"detail": "Could not validate credentials"}
            refresh_token_diff = DeepDiff(refresh_token_expected_response, refresh_token_response_json)
            assert not refresh_token_diff, refresh_token_diff  # prints out the differences if any


@pytest.mark.asyncio
async def test_get_initial_message():
    mocked_ai_agent = MockAgent()

    async with get_client() as client:
        with patch.object(LIFAIAgent, "setup", new=AsyncMock(return_value=mocked_ai_agent)):
            # Login to gather an access token

            login_response_json = await login_user_to_lif_advisor(
                client=client, username=USER_DETAILS_ALEX["username"], password=USER_DETAILS_ALEX["password"]
            )
            response_access_token = login_response_json.get("access_token", None)
            assert response_access_token is not None, "No access token in login response"

            # Retrieve the initial message

            auth_headers = {"Authorization": f"Bearer {response_access_token}"}
            initial_message_response = await client.get("/initial-message", headers=auth_headers)

            # Verify the response

            assert initial_message_response.status_code == 200
            initial_message_response_json = initial_message_response.json()
            initial_message_expected_response = {
                "content": "Hello Alan! Hang on for a second while I familiarize myself with your background.",
                "tokens": 0,
                "cost": 0.0,
            }
            diff = DeepDiff(initial_message_expected_response, initial_message_response_json)
            assert not diff, diff  # prints out the differences if any


@pytest.mark.asyncio
async def test_start_conversation_after_initialization():
    mocked_ai_agent = MockAgent()

    async with get_client() as client:
        with patch.object(LIFAIAgent, "setup", new=AsyncMock(return_value=mocked_ai_agent)) as setup_mock:
            # Login to gather an access token

            login_response_json = await login_user_to_lif_advisor(
                client=client, username=USER_DETAILS_ALEX["username"], password=USER_DETAILS_ALEX["password"]
            )
            response_access_token = login_response_json.get("access_token", None)
            assert response_access_token is not None, "No access token in login response"

            # Initialize the conversation

            auth_headers = {"Authorization": f"Bearer {response_access_token}"}
            initial_message_response = await client.get("/initial-message", headers=auth_headers)
            assert initial_message_response.status_code == 200, initial_message_response.text

            # Retrieve the start conversation with the same user that logged in

            auth_headers = {"Authorization": f"Bearer {response_access_token}"}
            start_conversation_response = await client.post("/start-conversation", headers=auth_headers)

            # Verify the response

            assert start_conversation_response.status_code == 200, start_conversation_response.text
            start_conversation_response_json = start_conversation_response.json()
            start_conversation_expected_response = {"content": "This is mocked content", "tokens": 10, "cost": 0.57}
            diff = DeepDiff(start_conversation_expected_response, start_conversation_response_json)
            assert not diff, diff  # prints out the differences if any

            # Verify the agent

            setup_mock.assert_awaited()
            mocked_ai_agent.ask_agent.assert_awaited_with(
                "load_profile",
                "Load my most recent interaction. Load other profile details including academic progress, coursework, skills, competencies, and credentials. And generate an appropriate response",
            )


@pytest.mark.asyncio
async def test_start_conversation_without_initialization():
    mocked_ai_agent = MockAgent()

    async with get_client() as client:
        with patch.object(LIFAIAgent, "setup", new=AsyncMock(return_value=mocked_ai_agent)) as setup_mock:
            # Login to gather an access token

            login_response_json = await login_user_to_lif_advisor(
                client=client, username=USER_DETAILS_ALEX["username"], password=USER_DETAILS_ALEX["password"]
            )
            response_access_token = login_response_json.get("access_token", None)
            assert response_access_token is not None, "No access token in login response"

            # NOT initializing conversation

            # Retrieve the start conversation

            auth_headers = {"Authorization": f"Bearer {response_access_token}"}
            start_conversation_response = await client.post("/start-conversation", headers=auth_headers)

            # Verify the failure response

            assert start_conversation_response.status_code == 400, start_conversation_response.text
            start_conversation_response_json = start_conversation_response.json()
            start_conversation_expected_response = {"detail": "Conversation not initialized"}
            diff = DeepDiff(start_conversation_expected_response, start_conversation_response_json)
            assert not diff, diff  # prints out the differences if any

            # Verify the agent

            setup_mock.assert_awaited_once()
            mocked_ai_agent.ask_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_continue_conversation_after_start():
    mocked_ai_agent = MockAgent()

    async with get_client() as client:
        with patch.object(LIFAIAgent, "setup", new=AsyncMock(return_value=mocked_ai_agent)) as setup_mock:
            # Login to gather an access token

            login_response_json = await login_user_to_lif_advisor(
                client=client, username=USER_DETAILS_ALEX["username"], password=USER_DETAILS_ALEX["password"]
            )
            response_access_token = login_response_json.get("access_token", None)
            assert response_access_token is not None, "No access token in login response"

            # Initialize conversation

            auth_headers = {"Authorization": f"Bearer {response_access_token}"}
            initial_message_response = await client.get("/initial-message", headers=auth_headers)
            assert initial_message_response.status_code == 200, initial_message_response.text

            # Start conversation

            start_conversation_response = await client.post("/start-conversation", headers=auth_headers)
            assert start_conversation_response.status_code == 200, start_conversation_response.text

            # Continue conversation

            continue_json = {"message": "What are my classes?"}
            continue_conversation_response = await client.post(
                "/continue-conversation", json=continue_json, headers=auth_headers
            )
            assert continue_conversation_response.status_code == 200, continue_conversation_response.text

            # Verify the response

            continue_conversation_response_json = continue_conversation_response.json()
            continue_conversation_expected_response = {"content": "This is mocked content", "tokens": 10, "cost": 0.57}
            diff = DeepDiff(continue_conversation_expected_response, continue_conversation_response_json)
            assert not diff, diff  # prints out the differences if any

            # Verify the agent

            setup_mock.assert_awaited()
            mocked_ai_agent.ask_agent.assert_awaited_with("continue_conversation", "What are my classes?")


@pytest.mark.asyncio
async def test_continue_conversation_before_start():
    mocked_ai_agent = MockAgent()

    async with get_client() as client:
        with patch.object(LIFAIAgent, "setup", new=AsyncMock(return_value=mocked_ai_agent)):
            # Login to gather an access token

            login_response_json = await login_user_to_lif_advisor(
                client=client, username=USER_DETAILS_ALEX["username"], password=USER_DETAILS_ALEX["password"]
            )
            response_access_token = login_response_json.get("access_token", None)
            assert response_access_token is not None, "No access token in login response"

            # Initialize conversation

            auth_headers = {"Authorization": f"Bearer {response_access_token}"}
            initial_message_response = await client.get("/initial-message", headers=auth_headers)
            assert initial_message_response.status_code == 200, initial_message_response.text

            # Do NOT start conversation

            # Continue conversation

            continue_json = {"message": "What are my classes?"}
            continue_conversation_response = await client.post(
                "/continue-conversation", json=continue_json, headers=auth_headers
            )
            assert continue_conversation_response.status_code == 400, continue_conversation_response.text

            # Verify the response

            continue_conversation_response_json = continue_conversation_response.json()
            continue_conversation_expected_response = {"detail": "Conversation not started"}
            diff = DeepDiff(continue_conversation_expected_response, continue_conversation_response_json)
            assert not diff, diff  # prints out the differences if any

            # Verify the agent

            mocked_ai_agent.ask_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_continue_conversation_before_initialize():
    mocked_ai_agent = MockAgent()

    async with get_client() as client:
        with patch.object(LIFAIAgent, "setup", new=AsyncMock(return_value=mocked_ai_agent)):
            # Login to gather an access token

            login_response_json = await login_user_to_lif_advisor(
                client=client, username=USER_DETAILS_ALEX["username"], password=USER_DETAILS_ALEX["password"]
            )
            response_access_token = login_response_json.get("access_token", None)
            assert response_access_token is not None, "No access token in login response"

            auth_headers = {"Authorization": f"Bearer {response_access_token}"}

            # Do NOT initialize conversation

            # Do NOT start conversation

            # Continue conversation

            continue_json = {"message": "What are my classes?"}
            continue_conversation_response = await client.post(
                "/continue-conversation", json=continue_json, headers=auth_headers
            )
            assert continue_conversation_response.status_code == 400, continue_conversation_response.text

            # Verify the response

            continue_conversation_response_json = continue_conversation_response.json()
            continue_conversation_expected_response = {"detail": "Conversation not started"}
            diff = DeepDiff(continue_conversation_expected_response, continue_conversation_response_json)
            assert not diff, diff  # prints out the differences if any

            # Verify the agent

            mocked_ai_agent.ask_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_logout():
    mocked_ai_agent = MockAgent()

    async with get_client() as client:
        with patch.object(LIFAIAgent, "setup", new=AsyncMock(return_value=mocked_ai_agent)):
            # Login to gather an access token

            login_response_json = await login_user_to_lif_advisor(
                client=client, username=USER_DETAILS_ALEX["username"], password=USER_DETAILS_ALEX["password"]
            )
            response_access_token = login_response_json.get("access_token", None)
            assert response_access_token is not None, "No access token in login response"

            # Logout

            logout_expected_response = {"success": True}
            await logout_user_from_lif_advisor(
                client=client, access_token=response_access_token, expected_response=logout_expected_response
            )

            # Verify the agent

            mocked_ai_agent.ask_agent.assert_awaited_with(
                "save_interaction_summary",
                "Summarize our conversation extracting metadata about the conversation and then save it",
            )

            # Confirm the refresh token is no longer valid

            response_refresh_token = login_response_json.get("refresh_token", None)
            assert response_refresh_token is not None, "No refresh token in login response"
            auth_headers = {"Authorization": f"Bearer {response_access_token}"}
            refresh_token_response = await client.post(
                "/refresh-token", json={"refresh_token": response_refresh_token}, headers=auth_headers
            )
            assert refresh_token_response.status_code == 401, refresh_token_response.text
            refresh_token_response_json = refresh_token_response.json()
            refresh_token_expected_response = {"detail": "Refresh token invalid or revoked"}
            refresh_token_diff = DeepDiff(refresh_token_expected_response, refresh_token_response_json)
            assert not refresh_token_diff, refresh_token_diff  # prints out the differences if any
