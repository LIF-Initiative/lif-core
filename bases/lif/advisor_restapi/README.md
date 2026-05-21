# `advisor_restapi` — Base

FastAPI base for the LIF Advisor: a conversational interface that lets a user query their own learner data through a LangChain/LangGraph agent. Pairs with the Advisor frontend (`frontends/lif_advisor_app/`).

## Endpoints
- `POST /login` — demo auth against an in-memory user list; returns access + refresh JWTs
- `POST /refresh-token` — exchange refresh token for a new access token
- `GET  /initial-message` — greeting message for a freshly-logged-in user
- `POST /start-conversation` — kicks off the conversation by loading the user's profile via the agent
- `POST /continue-conversation` — sends a user message, returns the agent's reply
- `POST /logout` — clears in-memory session state; agent summarizes the interaction first
- `GET  /health`

## Auth
HS256 JWTs minted/validated by `lif.auth.core`. Demo-grade — the user list (`users_db`) and password (`LIF_DEMO_USER_PASSWORD`) are hard-coded for demo purposes; not the self-serve auth path (see `docs/design/cross-cutting/self-serve-tenant-auth.md`).

## Composes
- `auth` — JWT helpers
- `langchain_agent` — `LIFAIAgent` wrapping LangChain/LangGraph + memory
- `logging`

## Deployed as
`projects/lif_advisor_api/`
