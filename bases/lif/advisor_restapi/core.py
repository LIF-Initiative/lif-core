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


# --- API Endpoints ---


@app.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """
    Authenticate a user and provide a JWT token.
    """
    user = next((user for user in users_db if user["username"] == request.username), None)
    if user and request.password == DEMO_USER_PASSWORD:
        access_token = create_access_token({"sub": user["username"]})
        refresh_token = create_refresh_token({"sub": user["username"]})
        refresh_tokens_store[user["username"]] = refresh_token
        conversation_states[user["username"]] = {
            "initialized": False,
            "identifier": user.get("identifier"),
            "identifier_type": user.get("identifier_type"),
            "identifier_type_enum": user.get("identifier_type_enum"),
            "greeting": user.get("firstname"),
            "conversation_thread_id": uuid.uuid4().hex,  # Unique thread ID for each conversation
        }

        username = user["username"]
        state = conversation_states.get(username)

        # Setup LIF AI Agent for this user conversation
        conversation_thread_id = state.get("conversation_thread_id")
        config = {}

        config["user_greeting"] = state.get("greeting")
        config["user_identifier"] = state.get("identifier")
        config["user_identifier_type"] = state.get("identifier_type")
        config["user_identifier_type_enum"] = state.get("identifier_type_enum")
        config["memory_config"] = {"configurable": {"thread_id": conversation_thread_id}}

        agent = await LIFAIAgent.setup(config)
        state["lif_ai_agent"] = agent

        return LoginResponse(
            success=True,
            message="Login successful",
            user=UserDetails(
                username=user["username"],
                firstname=user["firstname"],
                lastname=user["lastname"],
                identifier=user["identifier"],
                identifier_type=user["identifier_type"],
                identifier_type_enum=user["identifier_type_enum"],
            ),
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


@app.get("/initial-message", response_model=ChatMessage)
async def get_initial_message(username: str = Depends(get_current_user)) -> ChatMessage:
    """
    Provide the initial greeting message for a user.
    """
    if username not in conversation_states:
        conversation_states[username] = {"initialized": False}

    conversation_states[username]["initialized"] = True
    greeting = conversation_states[username].get("greeting", "there")

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
    state = conversation_states.get(username)
    if not state or not state.get("initialized", False):
        raise HTTPException(status_code=400, detail="Conversation not initialized")
    if state.get("started", False):
        raise HTTPException(status_code=400, detail="Conversation already started")
    state["started"] = True

    state = conversation_states.get(username)

    agent = state.get("lif_ai_agent")
    task = "load_profile"

    # TODO: Get this prompt from env variable
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
    state = conversation_states.get(username)
    if not state or not state.get("started", False):
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

    agent = state.get("lif_ai_agent")
    task = "save_interaction_summary"

    # TODO: Get this prompt from env variable
    response = await agent.ask_agent(
        task, "Summarize our conversation extracting metadata about the conversation and then save it"
    )
    # interaction_summary = json.loads(response['content'])

    logger.info(f"Summarization response: {response}")

    conversation_states.pop(username, None)
    refresh_tokens_store.pop(username, None)
    return LogoutResponse(success=True)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
