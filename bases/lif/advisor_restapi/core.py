import os
import uuid
from typing import Any, Dict, List

import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from lif.auth.core import create_access_token, create_refresh_token, decode_jwt, get_current_user
from lif.langchain_agent import LIFAIAgent
from lif.logging import get_logger

logger = get_logger(__name__)

DEMO_USER_PASSWORD = os.environ.get("LIF_DEMO_USER_PASSWORD", "changeme")

# --- Mock Database and State ---
users_db: List[Dict[str, Any]] = [
    {
        "username": "atsatrian_lifdemo@stateu.edu",
        "firstname": "Alan",
        "lastname": "Tsatrian",  # cspell:disable-line
        "identifier": "100001",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
    {
        "username": "jdiaz_lifdemo@stateu.edu",
        "firstname": "Jenna",
        "lastname": "Diaz",  # cspell:disable-line
        "identifier": "100002",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
    {
        "username": "smarin_lifdemo@stateu.edu",
        "firstname": "Sarah",
        "lastname": "Marin",
        "identifier": "100003",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
    {
        "username": "Rgreen11Fdemo@stateu.edu",
        "firstname": "Renee",
        "lastname": "Green",
        "identifier": "100004",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
    {
        "username": "tthatcher_lifdemo@stateu.edu",
        "firstname": "Tracy",
        "lastname": "Thatcher",
        "identifier": "100006",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
    {
        "username": "mhanson_lifdemo@stateu.edu",
        "firstname": "Matt",
        "lastname": "Hanson",
        "identifier": "100005",
        "identifier_type": "SCHOOL_ASSIGNED_NUMBER",
        "identifier_type_enum": "SCHOOL_ASSIGNED_NUMBER",
    },
]

conversation_states: Dict[str, Dict[str, Any]] = {}

# Store active refresh tokens: username -> token
refresh_tokens_store: Dict[str, str] = {}


app = FastAPI(title="LIF Advisor API", description="API for the LIF Advisor chat application", version="1.0.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)


# --- Pydantic Models ---
class LoginRequest(BaseModel):
    username: str
    password: str


class Question(BaseModel):
    message: str


class UserDetails(BaseModel):
    username: str
    firstname: str
    lastname: str
    identifier: str
    identifier_type: str
    identifier_type_enum: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    user: UserDetails
    access_token: str
    refresh_token: str


class ChatMessage(BaseModel):
    content: str
    tokens: int
    cost: float


class LogoutResponse(BaseModel):
    success: bool


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    access_token: str


class AgentConfig(BaseModel):
    """Typed config passed to ``LIFAIAgent.setup``. Serialized to a dict at the
    component boundary (the agent component consumes a plain mapping)."""

    user_greeting: str | None = None
    user_identifier: str | None = None
    user_identifier_type: str | None = None
    user_identifier_type_enum: str | None = None
    memory_config: Dict[str, Any]


# --- Session Helpers ---


def _find_user(username: str) -> Dict[str, Any] | None:
    """Look up a user record by username in the (mock) user store."""
    return next((user for user in users_db if user["username"] == username), None)


def _build_user_details(user: Dict[str, Any]) -> UserDetails:
    """Build the public UserDetails payload from a user record."""
    return UserDetails(
        username=user["username"],
        firstname=user["firstname"],
        lastname=user["lastname"],
        identifier=user["identifier"],
        identifier_type=user["identifier_type"],
        identifier_type_enum=user["identifier_type_enum"],
    )


async def _build_user_session(user: Dict[str, Any]) -> Dict[str, Any]:
    """Create a fresh conversation state and agent for a user, replacing any existing one.

    Used on login (every login starts a clean conversation) and as the rebuild
    step when a session has to be rehydrated after the process lost its in-memory
    state.
    """
    state: Dict[str, Any] = {
        "initialized": False,
        "started": False,
        "identifier": user.get("identifier"),
        "identifier_type": user.get("identifier_type"),
        "identifier_type_enum": user.get("identifier_type_enum"),
        "greeting": user.get("firstname"),
        "conversation_thread_id": uuid.uuid4().hex,  # Unique thread ID for each conversation
    }

    agent_config = AgentConfig(
        user_greeting=state["greeting"],
        user_identifier=state["identifier"],
        user_identifier_type=state["identifier_type"],
        user_identifier_type_enum=state["identifier_type_enum"],
        memory_config={"configurable": {"thread_id": state["conversation_thread_id"]}},
    )

    state["lif_ai_agent"] = await LIFAIAgent.setup(agent_config.model_dump())
    conversation_states[user["username"]] = state
    return state


async def _ensure_user_session(username: str) -> Dict[str, Any]:
    """Return the user's conversation state, rebuilding it if missing.

    Conversation state and the per-user agent live in memory and are set up at
    login. A page refresh (or a process restart) can leave a still-valid token
    with no matching server-side state; this lazily rebuilds it so the session
    keeps working instead of erroring.
    """
    state = conversation_states.get(username)
    if state and state.get("lif_ai_agent"):
        return state

    user = _find_user(username)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return await _build_user_session(user)


# --- API Endpoints ---


@app.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """
    Authenticate a user and provide a JWT token.
    """
    user = _find_user(request.username)
    if user and request.password == DEMO_USER_PASSWORD:
        access_token = create_access_token({"sub": user["username"]})
        refresh_token = create_refresh_token({"sub": user["username"]})
        refresh_tokens_store[user["username"]] = refresh_token

        # Every login starts a clean conversation + agent.
        await _build_user_session(user)

        return LoginResponse(
            success=True,
            message="Login successful",
            user=_build_user_details(user),
            access_token=access_token,
            refresh_token=refresh_token,
        )
    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/refresh-token", response_model=RefreshTokenResponse)
async def refresh_token(request: RefreshTokenRequest) -> RefreshTokenResponse:
    """
    Exchange a valid refresh token for a new access token.
    """
    try:
        payload = decode_jwt(request.refresh_token)
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        stored_token = refresh_tokens_store.get(username)
        if stored_token != request.refresh_token:
            raise HTTPException(status_code=401, detail="Refresh token invalid or revoked")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    access_token = create_access_token({"sub": username})
    return RefreshTokenResponse(access_token=access_token)


@app.get("/me", response_model=UserDetails)
async def get_me(username: str = Depends(get_current_user)) -> UserDetails:
    """
    Return the authenticated user's profile.

    Lets the frontend restore a session after a page refresh from the stored
    token alone, without persisting user details client-side.
    """
    user = _find_user(username)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _build_user_details(user)


@app.get("/initial-message", response_model=ChatMessage)
async def get_initial_message(username: str = Depends(get_current_user)) -> ChatMessage:
    """
    Provide the initial greeting message for a user.
    """
    state = await _ensure_user_session(username)
    state["initialized"] = True
    greeting = state.get("greeting", "there")

    return ChatMessage(
        content=f"Hello {greeting}! Hang on for a second while I familiarize myself with your background.",
        tokens=0,
        cost=0.0,
    )


@app.post("/start-conversation", response_model=ChatMessage)
async def start_conversation(username: str = Depends(get_current_user)) -> ChatMessage:
    """
    Start a new conversation by summarizing the user's background.
    """
    state = await _ensure_user_session(username)
    if not state.get("initialized", False):
        raise HTTPException(status_code=400, detail="Conversation not initialized")
    if state.get("started", False):
        # Idempotent: a refreshed/restored session already has an active
        # conversation, so welcome the user back instead of erroring.
        return ChatMessage(content="Welcome back! We can pick up right where we left off.", tokens=0, cost=0.0)
    state["started"] = True

    agent = state.get("lif_ai_agent")
    task = "load_profile"

    # TODO(#986): move this hard-coded query prompt to env/config
    query = "Load my most recent interaction. Load other profile details including academic progress, coursework, skills, competencies, and credentials. And generate an appropriate response"

    response = await agent.ask_agent(task, query)

    return ChatMessage(
        content=f"{response.get('content', '')}", tokens=response.get("tokens", 0), cost=response.get("cost", 0.0)
    )


@app.post("/continue-conversation", response_model=ChatMessage)
async def continue_conversation(question: Question, username: str = Depends(get_current_user)) -> ChatMessage:
    """
    Continue an ongoing conversation with the LIF agent.
    """
    state = await _ensure_user_session(username)
    if not state.get("started", False):
        raise HTTPException(status_code=400, detail="Conversation not started")

    agent = state.get("lif_ai_agent")
    task = "continue_conversation"

    query = question.message.strip()
    response = await agent.ask_agent(task, query)

    return ChatMessage(
        content=response.get("content", ""), tokens=response.get("tokens", 0), cost=response.get("cost", 0.0)
    )


@app.post("/logout", response_model=LogoutResponse)
async def logout(username: str = Depends(get_current_user)) -> LogoutResponse:
    """
    Logout a user and clear their conversation state and refresh token.
    """
    state = conversation_states.get(username)

    # Only summarize when there's a live agent — a session restored after a
    # process restart may have no in-memory state, and logout must still succeed.
    if state and state.get("lif_ai_agent"):
        agent = state["lif_ai_agent"]
        task = "save_interaction_summary"

        # TODO(#986): move this hard-coded query prompt to env/config
        response = await agent.ask_agent(
            task, "Summarize our conversation extracting metadata about the conversation and then save it"
        )
        logger.info(f"Summarization response: {response}")

    conversation_states.pop(username, None)
    refresh_tokens_store.pop(username, None)
    return LogoutResponse(success=True)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
