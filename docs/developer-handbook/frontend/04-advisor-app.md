# 4. The Advisor app

The chat client for the Advisor: what each screen calls, what the Advisor API does with it, and how login is kept alive.

*Checked against main `2967cb9`, November 2026.* Install, lint, test, build and type-check were run; chatting needs an OpenAI key and wasn't run.

---

## What it is

A small React app (17 TypeScript files) in `frontends/lif_advisor_app/`. A demo learner logs in, and the
Advisor, an LLM agent in the Advisor API (`bases/lif/advisor_restapi/`), greets them using their LIF
record and answers questions about it. The app only displays the conversation; everything the Advisor knows
or says comes from the Advisor API.

```
src/
  App.tsx              login state: restores a session on load, shows LoginPanel or ChatInterface
  components/          LoginPanel, ChatInterface, MessageList, MessageItem, MessageInput, Banner
  hooks/useChat.ts     the conversation: which endpoint to call when, and the message list
  utils/axios.ts       the axios instance: adds the token, refreshes it on 401
  config/chat.ts       chat settings
  types/               shared types (Message, UserDetails)
```

## What you can do without an OpenAI key

The Advisor API needs `OPENAI_API_KEY` for anything that reaches the LLM. Without one you can still install,
lint, test, type-check and build the app, and work on its layout and styling. Chat itself won't work. The app
shows its own error message ("I'm having trouble…") in the chat when a call fails. This handbook didn't run
the Advisor with or without a key, so which step fails first without one is untested.

## A conversation, call by call

| When | The app calls | The Advisor API does | Reaches the LLM? |
|---|---|---|---|
| Log in (`LoginPanel`) | `POST /login` with a persona's username and the demo password | Checks the password, issues an access and a refresh token, and starts a fresh conversation and agent for that user | No |
| Page load, logged in (`App.tsx`) | `GET /me` | Returns the user for the stored token, so a reload keeps you logged in | No |
| Chat opens (`useChat`) | `GET /initial-message` | Returns a fixed greeting: "Hello *name*! Hang on for a second while I familiarize myself with your background." | No |
| Two seconds later | `POST /start-conversation` | Runs the agent's `load_profile` task: it reads the learner's record (through the Semantic Search server and the GraphQL API) and writes an opening summary. Calling it again returns "Welcome back!" | **Yes** |
| Each message you send | `POST /continue-conversation` with `{message}` | Runs the agent's `continue_conversation` task | **Yes** |
| Log out (`App.tsx`) | `POST /logout` | Answers at once, then asks the agent to summarize and save the conversation in the background; forgets the user's conversation and refresh token | Yes, after answering |

Each answer has `content` (Markdown), `tokens` and `cost`. `MessageItem` renders the Markdown with
`react-markdown` and `remark-gfm` and, when both are above zero, shows the tokens and cost under the
message.

`/continue-conversation` is called with `timeout: 0`, meaning no timeout: an LLM answer can take a while.

**Conversations live in the Advisor API's memory.** Restarting it forgets every conversation and refresh
token. A user with a still-valid access token gets a new conversation rebuilt on their next call; one whose
access token has expired has to log in again, because the refresh token is gone too.

## Login and tokens

The tokens are stored in `localStorage` as `token` and `refreshToken`. `src/utils/axios.ts` does the rest:

1. **Every request** gets `Authorization: Bearer <token>` (a request interceptor).
2. **On a `401`**, the response interceptor posts the refresh token to `/refresh-token`, stores the new access
   token, and repeats the request.
3. **Several requests failing at once** share one refresh: the first starts it, the rest wait in a queue and are
   repeated when it finishes.
4. **If the refresh fails**, the session is over: the tokens are removed and the browser goes to `/login`.

Two endpoints are exempt from the refresh, and the comments in `axios.ts` explain why. A `401` from `/login`
means wrong password, which `LoginPanel` has to show. A `401` from `/refresh-token` means the refresh token
is dead; retrying it would loop forever, which was bug #527. `/logout` is deliberately *not* exempt, so an
expired session can still reach the server and revoke its refresh token. Read those comments before changing
the interceptor; `utils/axios.test.ts` tests these cases.

## Building the image

The app's own README is out of date on Docker: there is no `docker/Dockerfile`, and the build arg is not
`LIF_MCP_AGENT_URL`. The real command is:

```bash
cd frontends/lif_advisor_app
docker build --build-arg LIF_ADVISOR_API_URL=http://localhost:8004 -t lif_advisor_app .
docker run -d -p 5174:80 lif_advisor_app
```

As with the MDR UI, the URL is fixed at build time and must be one the browser can reach
([chapter 0](00-start-here.md)).

## Before you push

The Advisor app's `npm run build` doesn't type-check, and nothing in CI does. Run
`npx tsc --noEmit -p tsconfig.app.json` yourself ([chapter 6](06-checks-ci-and-shipping.md)).

## Where to go next

The Advisor API and its agent are backend code: `bases/lif/advisor_restapi/` and the `langchain_agent`
component (backend [chapter 2](../backend/02-codebase-map.md)).
