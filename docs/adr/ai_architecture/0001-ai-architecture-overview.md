# ADR 0001: AI Architecture Overview

**Status:** Accepted
**Date:** 2025-02-02
**Authors:** Architecture Team

## Context

The Learner Information Framework (LIF) requires AI capabilities to provide personalized career guidance to learners based on their academic records, credentials, skills, and employment history. The system needs to:

1. Understand natural language queries about learner data
2. Search across complex, nested learner records semantically
3. Provide conversational, asset-based mentoring
4. Track conversation context and costs

## Decision

We implemented a multi-layer AI architecture combining:

- **OpenAI GPT models** for natural language understanding and generation
- **LangChain/LangGraph** for agent orchestration and tool use
- **Model Context Protocol (MCP)** for structured tool access
- **Sentence Transformers** for semantic search embeddings

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User Interface                              │
│                    (lif-advisor-app - React)                        │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │ HTTP
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Advisor API (Port 8004)                        │
│                    FastAPI + LangChain Agent                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    LIFAIAgent                                │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐    │   │
│  │  │ load_profile │  │  continue_   │  │ save_interaction │    │   │
│  │  │    agent     │  │ conversation │  │  _summary agent  │    │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘    │   │
│  │           │                │                  │              │   │
│  │           └────────────────┼──────────────────┘              │   │
│  │                            ▼                                 │   │
│  │              ┌─────────────────────────┐                     │   │
│  │              │   LangGraph ReAct Agent │                     │   │
│  │              │   (ChatOpenAI + Tools)  │                     │   │
│  │              └────────────┬────────────┘                     │   │
│  │                           │                                  │   │
│  │              ┌────────────▼────────────┐                     │   │
│  │              │    MCP Client Adapter   │                     │   │
│  │              │ (langchain-mcp-adapters)│                     │   │
│  │              └────────────┬────────────┘                     │   │
│  └───────────────────────────┼──────────────────────────────────┘   │
└──────────────────────────────┼──────────────────────────────────────┘
                               │ MCP Protocol (HTTP)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│              Semantic Search MCP Server (Port 8003)                 │
│                        FastMCP Framework                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                   SchemaStateManager                         │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌────────────────────┐    │   │
│  │  │   Schema    │  │  Sentence   │  │     Embeddings     │    │   │
│  │  │  (from MDR) │  │ Transformer │  │  (all LIF fields)  │    │   │
│  │  └─────────────┘  └─────────────┘  └────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      MCP Tools                               │   │
│  │  ┌─────────────────────┐  ┌────────────────────────────┐     │   │
│  │  │     lif_query       │  │       lif_mutation         │     │   │
│  │  │ (semantic search +  │  │   (update learner data)    │     │   │
│  │  │  GraphQL generation)│  │                            │     │   │
│  │  └─────────────────────┘  └────────────────────────────┘     │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ GraphQL
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    GraphQL API (Port 8010)                          │
│              Strawberry GraphQL + Query Planner                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         MongoDB / Data Layer                        │
│                      (Learner Information Records)                  │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. LLM Provider: OpenAI

**Why OpenAI:**
- Best-in-class performance for conversational AI
- Robust function/tool calling capabilities
- Predictable pricing model
- Wide LangChain ecosystem support

**Model Selection:**

| Model | Input Cost | Output Cost | Use Case |
|-------|-----------|-------------|----------|
| `gpt-4o-mini` | $1.10/1M | $4.40/1M | Default, balanced |
| `gpt-4.1-mini` | $0.40/1M | $1.60/1M | Cost-optimized |
| `gpt-4.1-nano` | $0.10/1M | $0.40/1M | High-volume, simple |
| `gpt-4.1` | $2.00/1M | $8.00/1M | Complex reasoning |

**Configuration:**
```python
ChatOpenAI(
    model_name=LLM_MODEL_NAME,  # via LIF_ADVISOR_LLM_MODEL_NAME env var
    temperature=0.0,            # Deterministic responses
)
```

### 2. Agent Framework: LangChain + LangGraph

**Why LangChain/LangGraph:**
- Industry standard for LLM application development
- Native MCP adapter support
- ReAct agent pattern for tool use
- Built-in checkpointing and state management

**Agent Architecture:**
```python
# LangGraph ReAct Agent with MCP tools
agent = create_react_agent(
    model=ChatOpenAI(...),
    tools=mcp_tools,           # lif_query, lif_mutation
    prompt=system_prompt,
    state_schema=ChatState,    # Custom state with context
    pre_model_hook=pre_hook,   # Memory summarization
    checkpointer=InMemorySaver(),
)
```

**Three Task-Specific Agents:**

1. **load_profile** - Initial learner profile analysis
   - Retrieves academic progress, credentials, skills
   - Generates personalized greeting with strengths/opportunities
   - Max 250 words

2. **continue_conversation** - Ongoing mentoring dialogue
   - Asset-based career guidance approach
   - Uses semantic search to find relevant learner data
   - Generates follow-up questions
   - Max 200 words

3. **save_interaction_summary** - Session wrap-up
   - Extracts conversation metadata (sentiment, severity)
   - Persists summary to learner record via mutation

### 3. Model Context Protocol (MCP)

**Why MCP:**
- Anthropic's open standard for LLM tool integration
- Clean separation between LLM and data access
- Structured, type-safe tool definitions
- Reusable across different LLM providers

**MCP Server Implementation:**
```
Framework: FastMCP v2.9
Endpoint:  POST /mcp
Health:    GET /health
Status:    GET /schema/status
```

**MCP Tools:**

| Tool | Purpose | Input | Output |
|------|---------|-------|--------|
| `lif_query` | Semantic search + data retrieval | Natural language query + filter | GraphQL results |
| `lif_mutation` | Update learner records | Field path + new value | Success/failure |

**Tool Flow (lif_query):**
1. Receive natural language query
2. Embed query using SentenceTransformer
3. Find top-k matching schema fields by cosine similarity
4. Generate GraphQL query from matched paths
5. Execute against GraphQL API
6. Return structured results to agent

### 4. Semantic Search & Embeddings

**Why Sentence Transformers:**
- Open source, no API costs for embeddings
- Fast inference, can run on CPU
- Good quality for semantic similarity
- Self-hosted, no data leaves infrastructure

**Embedding Strategy:**
```python
# At startup: embed all LIF schema field descriptions
embeddings = model.encode(
    [leaf.description for leaf in schema_leaves],
    normalize_embeddings=True
)

# At query time: embed query and find similar fields
query_embedding = model.encode([user_query], normalize_embeddings=True)
similarities = np.dot(embeddings, query_embedding.T).flatten()
top_matches = np.argsort(-similarities)[:top_k]
```

**Schema Fields Indexed:**
- All Person entity fields (Name, Contact, Identifier, etc.)
- Proficiency records with descriptions
- Credential awards and courses
- Employment learning experiences
- Position and employment preferences

### 5. Memory Management

**Challenge:** Long conversations exceed context limits and increase costs.

**Solution:** LangMem-based summarization with configurable thresholds.

```python
# Configuration
LIF_ADVISOR_MESSAGES_TO_KEEP = 4       # Recent messages retained
LIF_ADVISOR_MAX_CONVERSATION_SIZE = 2048  # Tokens before summarization
LIF_ADVISOR_MAX_SUMMARY_SIZE = 1024    # Max summary tokens

# Pre-model hook summarizes if conversation exceeds limits
def pre_model_hook(state):
    if count_tokens(state.messages) > MAX_CONVERSATION_SIZE:
        state.messages = summarize_messages(state.messages)
    return state
```

### 6. Cost Tracking

Every response includes token usage and cost calculation:

```python
class ChatMessage:
    content: str
    tokens: dict  # {input, output, cached}
    cost: float   # USD
```

Cost calculation accounts for:
- Input tokens (full price)
- Output tokens (higher price)
- Cached tokens (reduced price for repeated prompts)

## Data Flow Example

**User asks:** "What skills does this learner have in data analysis?"

1. **Advisor API** receives query, routes to `continue_conversation` agent
2. **Query Reframing** adds learner identifier and expands "data analysis" with synonyms
3. **LangGraph Agent** decides to use `lif_query` tool
4. **MCP Client** sends tool call to Semantic Search server
5. **Semantic Search**:
   - Embeds "data analysis skills"
   - Finds matches: `Proficiency.name`, `Proficiency.description`, `CourseLearningExperience`
   - Generates GraphQL query with filters
6. **GraphQL API** returns matching proficiencies and courses
7. **Agent** synthesizes response with specific skill recommendations
8. **Memory Hook** checks if summarization needed
9. **Response** returned with content, tokens, and cost

## File Structure

```
bases/
├── lif/
│   ├── advisor_restapi/           # FastAPI advisor service
│   │   └── core.py                # REST endpoints
│   └── semantic_search_mcp_server/ # MCP server
│       └── core.py                # MCP tool definitions

components/
└── lif/
    ├── langchain_agent/           # Agent implementation
    │   ├── core.py                # LIFAIAgent class
    │   ├── memory.py              # Summarization logic
    │   └── prompts/               # System prompts
    │       ├── load_profile.txt
    │       ├── continue_conversation.txt
    │       ├── save_interaction_summary.txt
    │       └── prompt_template_query.txt
    ├── semantic_search_service/   # Search logic
    │   └── core.py                # Embedding + search
    └── schema_state_manager/      # Schema loading
        └── core.py                # MDR integration
```

## Dependencies

```toml
# AI/ML Core
langchain = "~0.3"
langchain-openai = "~0.3"
langgraph = "~0.4"
langgraph-prebuilt = "~0.2"
langmem = "~0.0"

# MCP
fastmcp = "~2.9"
mcp = ">=1.10,<2.0"
langchain-mcp-adapters = ">=0.1.14,<0.2.0"

# Embeddings
sentence-transformers = "~4.1"
numpy = "~2.3"
```

## Configuration Reference

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `LIF_ADVISOR_LLM_MODEL_NAME` | GPT model to use | `gpt-4o-mini` |
| `LIF_SEMANTIC_SEARCH_MCP_SERVER_URL` | MCP server endpoint | `http://localhost:8003/mcp` |
| `LIF_GRAPHQL_API_URL` | GraphQL backend | `http://localhost:8010/graphql` |
| `LIF_ADVISOR_MESSAGES_TO_KEEP` | Messages before summarization | `4` |
| `LIF_ADVISOR_MAX_CONVERSATION_SIZE` | Token limit for context | `2048` |
| `LIF_ADVISOR_MAX_SUMMARY_SIZE` | Max summary tokens | `1024` |
| `LIF_SEMANTIC_SEARCH_MODEL_NAME` | Embedding model | `all-MiniLM-L6-v2` |

## Consequences

### Positive
- **Modular Architecture:** MCP separates LLM logic from data access
- **Cost Visibility:** Token tracking enables usage monitoring
- **Flexible Models:** Easy to swap LLM providers or models
- **Self-hosted Embeddings:** No API costs for semantic search
- **Conversation Memory:** Long sessions handled gracefully

### Negative
- **OpenAI Dependency:** Primary LLM tied to single provider
- **Cold Start:** Embedding computation adds startup time (~10-15s)
- **Memory Overhead:** In-memory checkpointing limits horizontal scaling

### Risks
- **API Rate Limits:** High usage could hit OpenAI rate limits
- **Cost Overruns:** Verbose prompts or long conversations increase costs
- **Model Deprecation:** OpenAI model changes require configuration updates

## Future Considerations

1. **Multi-provider LLM Support:** Add Anthropic Claude, local models via Ollama
2. **Persistent Checkpointing:** PostgreSQL-based conversation state for scaling
3. **Streaming Responses:** Real-time token streaming for better UX
4. **Fine-tuned Models:** Domain-specific fine-tuning for career guidance
5. **Vector Database:** Replace in-memory embeddings with Pinecone/Weaviate for scale

## Related Documents

- [MCP Specification](https://modelcontextprotocol.io/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference)
