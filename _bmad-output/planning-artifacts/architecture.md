---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-03-23'
inputDocuments:
  - product-brief-bmad.md
  - product-brief-bmad-distillate.md
  - prd.md
  - research/domain-research-report.md
  - research/technical-data360-voice-stack-research-2026-03-23.md
workflowType: 'architecture'
project_name: 'Data360 Voice'
user_name: 'Felipe'
date: '2026-03-23'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements (36 total, 6 categories):**

| Category | FRs | Architectural Impact |
|----------|-----|---------------------|
| Data Query & Retrieval | FR1-7 | MCP server tools, vector search integration, multi-country support |
| Citation & Source Attribution | FR8-12 | DATA_SOURCE passthrough pipeline, response formatting |
| Narrative Response Generation | FR13-17 | LLM prompt design, transparent failure handling |
| LLM Grounding & Trust | FR18-22 | System prompt constraints, grounding boundary enforcement |
| Fact-Check Mode | FR23-26 | Claim parsing, verdict generation, comparative data flow |
| Conversation Management | FR27-30 | Chainlit datalayer, PostgreSQL persistence, streaming |
| MCP Server / Data Integration | FR31-36 | Dual transport, pagination, 3 Data360 API endpoints |

**Non-Functional Requirements (12 total):**

| Category | NFRs | Architectural Impact |
|----------|------|---------------------|
| Performance | NFR1-4 | Streaming latency (<3s first token), caching strategy (API responses in PostgreSQL), 10-50 concurrent sessions |
| Security | NFR5-8 | Environment variable secrets, HTTPS-only external comms, no PII storage |
| Integration | NFR9-12 | Graceful API failure handling, rate limit backoff, configurable cache TTL, transport-agnostic MCP server |

**Scale & Complexity:**

- Primary domain: Full-stack web (conversational AI with institutional data integration)
- Complexity level: Medium
- Estimated architectural components: 5 (MCP Server, FastAPI Backend, Chainlit Frontend, Claude API Integration, PostgreSQL Data Layer)

### Technical Constraints & Dependencies

- **Data360 API (Beta):** No auth required, but beta status means breaking changes are possible. Aggressive caching + abstracted client mitigate this.
- **Country-level granularity only:** No sub-national data. System must communicate this limitation transparently (FR17, Journey 5).
- **Pagination cap:** Max 1000 records per API call. MCP server must handle automatic pagination for large result sets (FR34).
- **Claude API dependency:** Haiku 4.5 for production, Sonnet for complex queries. Prompt caching critical for cost control.
- **Chainlit framework:** Provides native MCP client, Socket.IO streaming, and PostgreSQL datalayer, but limits UI customization.
- **Challenge timeline:** EOI by Mar 31, prototype by May 31. MCP server is the critical path for Week 1.

### Cross-Cutting Concerns Identified

- **Citation integrity:** DATA_SOURCE must flow from API response through MCP tool result to LLM output without modification. This is the core trust proposition.
- **Data freshness transparency:** Every response must show the most recent data year and warn when >2 years old.
- **Transparent failure:** "No data found" must be explicit and honest across all components (MCP server, LLM responses, UI).
- **Caching strategy:** Spans MCP server (API response cache), backend (indicator metadata), and database (PostgreSQL with TTL).
- **Dual transport:** MCP server must work identically via stdio (Claude Desktop dev) and HTTP Streamable (Chainlit production).
- **Error propagation:** API unavailability, rate limits, and data gaps must surface clearly to the user, not be swallowed silently.

## Starter Template Evaluation

### Primary Technology Domain

Python full-stack web (conversational AI), based on project requirements. All core dependencies are Python-native, no separate frontend build pipeline needed (Chainlit handles UI).

### Starter Options Considered

| Option | What it provides | Verdict |
|--------|-----------------|---------|
| FastAPI Full Stack Template | React frontend, SQLModel, Docker, auth | Overkill, includes React (we use Chainlit), PostgreSQL setup is useful but template is opinionated differently |
| `create-fastapi-project` | Scaffolded FastAPI with DB options | Adds unnecessary abstraction for this scope |
| Manual project setup | Full control, minimal boilerplate | Best fit, since Chainlit + FastMCP have no scaffolding CLIs and the project structure is simple |

### Selected Approach: Manual Project Setup

**Rationale:** The core tools (FastMCP 3.1.1, Chainlit 2.10.0, FastAPI 0.135.2) all follow a "create your entry file manually" pattern. No existing scaffold combines all three. A custom structure gives us exactly what we need without fighting a template's opinions.

**Initialization Commands:**

```bash
# Project setup with uv
uv init data360-voice
cd data360-voice
uv add fastmcp chainlit fastapi uvicorn asyncpg anthropic httpx

# Chainlit config
chainlit init
```

**Architectural Decisions (Manual Starter):**

**Language & Runtime:**
- Python 3.11+ (better async performance)
- Type hints throughout (FastMCP auto-generates schemas from them)
- uv for dependency management

**Project Structure:**

```
data360-voice/
├── mcp_server/           # MCP server (standalone, dual transport)
│   ├── __init__.py
│   ├── server.py         # FastMCP server definition + tools
│   └── data360_client.py # World Bank API client (abstracted)
├── app/                  # Web application
│   ├── __init__.py
│   ├── main.py           # FastAPI app + Chainlit mount
│   ├── chat.py           # Chainlit handlers (@cl.on_message, etc.)
│   └── config.py         # Settings and environment variables
├── .chainlit/
│   └── config.toml       # Chainlit configuration
├── pyproject.toml         # uv project config
├── Dockerfile
└── .env.example
```

**Build Tooling:**
- uv for package management and virtual environments
- Docker for deployment
- No separate frontend build step (Chainlit serves UI)

**Testing Framework:**
- pytest + httpx for FastAPI endpoint testing
- MCP Inspector for MCP server debugging
- Claude Desktop for end-to-end MCP testing (stdio)

**Development Experience:**
- `fastmcp dev` for MCP server development with Inspector
- `chainlit run` for chat UI development with hot reload
- `uvicorn app.main:app --reload` for full app development

**Note:** MCP server (`mcp_server/`) is designed as a standalone module, testable independently via stdio before web integration.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
1. MCP tool-to-API mapping: 5 thin wrapper tools, 1:1 with Data360 endpoints
2. Data360 API parameter mapping: official OpenAPI spec as source of truth
3. Auto-pagination strategy: silent, 5000 record cap
4. Dual transport: stdio primary (Claude Desktop testing), HTTP Streamable secondary (both from day 1)

**Important Decisions (Shape Architecture):**
5. No auth layer for MVP
6. Structured error responses from MCP tools (LLM narrates failures)
7. httpx async client with retry for Data360 API
8. Python stdlib logging (structured JSON in prod)

**Deferred Decisions (Post-Week 1):**
- Infrastructure & deployment (Docker, Railway/Render)
- CI/CD pipeline
- User authentication
- Caching layer (PostgreSQL cache tables)

### Data Architecture

**MCP Server API Mapping (Source: [Data360 OpenAPI Spec](https://raw.githubusercontent.com/worldbank/open-api-specs/refs/heads/main/Data360%20Open_API.json))**

| MCP Tool | HTTP Method | Endpoint | Required Params | Key Optional Params |
|----------|------------|----------|----------------|-------------------|
| `search_indicators` | POST | `/data360/searchv2` | `search` | `top`, `skip`, `filter` |
| `get_data` | GET | `/data360/data` | `DATABASE_ID` | `INDICATOR`, `REF_AREA`, `TIME_PERIOD`, `timePeriodFrom`, `timePeriodTo`, `skip` |
| `get_metadata` | POST | `/data360/metadata` | `query` (OData string) | - |
| `list_indicators` | GET | `/data360/indicators` | `datasetId` | - |
| `get_disaggregation` | GET | `/data360/disaggregation` | `datasetId` | `indicatorId` |

**Tool Signatures:**

```python
@mcp.tool()
async def search_indicators(
    query: str,                      # maps to "search"
    top: int = 10,                   # max results per page
    skip: int = 0,                   # pagination offset
    filter: str | None = None,       # OData filter expression
) -> dict:
    """Search World Bank Data360 indicators using natural language.
    Returns ranked indicator matches with metadata."""

@mcp.tool()
async def get_data(
    database_id: str,                # required, e.g. "WB_WDI"
    indicator: str | None = None,    # e.g. "WB_WDI_EN_ATM_CO2E_KT"
    ref_area: str | None = None,     # country ISO code, e.g. "BRA", "WLD"
    time_period: str | None = None,  # specific year
    time_period_from: str | None = None,
    time_period_to: str | None = None,
    skip: int = 0,
) -> dict:
    """Retrieve data values for indicators by country and time period.
    Response includes OBS_VALUE, DATA_SOURCE, COMMENT_TS, LATEST_DATA fields.
    Auto-paginates up to 5000 records."""

@mcp.tool()
async def get_metadata(
    query: str,  # OData filter, e.g. "&$filter=series_description/idno eq 'WB_WDI_SP_POP_TOTL'"
) -> dict:
    """Get detailed metadata about indicators, datasets, and topics.
    Supports OData $filter and $select syntax."""

@mcp.tool()
async def list_indicators(
    dataset_id: str,  # e.g. "WB_WDI"
) -> dict:
    """List all available indicators in a given dataset."""

@mcp.tool()
async def get_disaggregation(
    dataset_id: str,
    indicator_id: str | None = None,
) -> dict:
    """Get available disaggregation dimensions (SEX, AGE, URBANISATION, etc.) for an indicator."""
```

**Data Flow (Query Lifecycle):**

```
User question (natural language)
    │
    ▼
Claude selects tools based on intent
    │
    ▼
search_indicators(query="drought Brazil")
    │ returns: indicator IDs, names, database_ids
    ▼
get_data(database_id="WB_WDI", indicator="WB_WDI_...", ref_area="BRA")
    │ returns: OBS_VALUE, DATA_SOURCE, COMMENT_TS, TIME_PERIOD, LATEST_DATA
    │ (auto-paginates if >1000 records, caps at 5000)
    ▼
Claude generates narrative with DATA_SOURCE citations
```

**Critical Response Fields for Citation Integrity:**

| Field | Purpose | Passed to LLM |
|-------|---------|---------------|
| `DATA_SOURCE` | Source attribution for citations | Always |
| `COMMENT_TS` | Human-readable data description | Always |
| `OBS_VALUE` | Actual data value | Always |
| `TIME_PERIOD` | Year of the data point | Always |
| `LATEST_DATA` | Whether this is the most recent value | Always |
| `INDICATOR` | Indicator code for reference | Always |
| `REF_AREA` | Country/region code | Always |

**Pagination Strategy:**
- MCP tools auto-paginate internally using `skip` parameter
- Loop in increments of 1000 (API max per call)
- Hard cap at 5000 records total per tool call
- Return `total_count` from API alongside results so LLM knows if data was truncated

**API Client Design (`data360_client.py`):**
- httpx.AsyncClient with configurable timeout and retry
- Maps friendly Python snake_case params to API UPPERCASE params
- Single shared client instance per MCP server lifecycle
- Base URL: `https://data360api.worldbank.org`

### Authentication & Security

- No auth layer for MVP
- Claude API key: environment variable only
- World Bank Data360 API: public, no auth required
- No PII collected or stored
- HTTPS for all external API communication

### API & Communication Patterns

- **MCP transport:** Both stdio and HTTP Streamable from day 1 (FastMCP transport flag switch)
- **Primary dev workflow:** stdio with Claude Desktop for testing
- **Error handling:** MCP tools return structured error objects, never raise exceptions. The LLM receives error context and narrates failures transparently to users.
- **HTTP client:** httpx async with exponential backoff retry for Data360 API

### Frontend Architecture

Chainlit handles all frontend concerns. No custom frontend decisions needed for MVP.

### Infrastructure & Deployment

Deferred past Week 1. When needed:
- Docker single container (Uvicorn ASGI)
- Railway or Render with managed PostgreSQL
- GitHub Actions for CI/CD
- Python stdlib logging (structured JSON in prod)

### Decision Impact Analysis

**Implementation Sequence:**
1. `data360_client.py` - async API client with pagination logic
2. `server.py` - FastMCP server with 5 tool definitions
3. Test via `fastmcp dev` (Inspector) and Claude Desktop (stdio)
4. Add HTTP Streamable transport flag for production readiness

**Cross-Component Dependencies:**
- MCP tool response format directly affects LLM prompt design (DATA_SOURCE, COMMENT_TS must be preserved)
- `DATABASE_ID` requirement means `search_indicators` must return database info so `get_data` can use it
- Auto-pagination in `data360_client.py` is shared across `get_data` and potentially `list_indicators`

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified:** 5 areas where AI agents could make different choices

### Naming Patterns

**Python Code Naming:**
- Functions, variables, parameters: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods/attributes: `_leading_underscore`
- Module files: `snake_case.py`

**API Parameter Mapping:**
The Data360 API uses UPPERCASE params (`DATABASE_ID`, `REF_AREA`, `INDICATOR`). MCP tool signatures use snake_case (`database_id`, `ref_area`, `indicator`). The `data360_client.py` handles the mapping:

```python
# Tool signature (snake_case, user-friendly)
async def get_data(database_id: str, ref_area: str | None = None) -> dict:
    ...

# Client maps to API params (UPPERCASE)
params = {"DATABASE_ID": database_id, "REF_AREA": ref_area}
```

**Database Naming (when PostgreSQL is added):**
- Tables: `snake_case`, plural (`api_cache_entries`, `conversations`)
- Columns: `snake_case` (`created_at`, `indicator_id`)
- Chainlit-datalayer tables: leave as-is (managed by Chainlit)

### Structure Patterns

**Project Organization:**
- Organize by component, not by type (`mcp_server/`, `app/`, not `models/`, `services/`)
- Tests: `tests/` directory at project root, mirroring source structure
- No `utils.py` dumping ground, if a helper is needed, put it in the module that uses it

```
tests/
├── mcp_server/
│   ├── test_server.py
│   └── test_data360_client.py
└── app/
    └── test_main.py
```

**Configuration:**
- Environment variables via `.env` file (loaded by pydantic-settings or python-dotenv)
- Single `config.py` per component that needs it
- No hardcoded URLs, API keys, or magic numbers

### Format Patterns

**MCP Tool Response Format:**
All tools return a consistent structure:

```python
# Success response
{
    "success": True,
    "data": [...],          # actual API response data
    "total_count": 1234,    # total available records
    "returned_count": 100,  # records in this response
    "truncated": False,     # True if hit 5000 cap
}

# Error response
{
    "success": False,
    "error": "Data360 API returned 503: Service Unavailable",
    "error_type": "api_error",  # api_error | validation_error | timeout
}
```

**JSON Field Naming:**
- Internal Python code: `snake_case`
- MCP tool responses: `snake_case`
- Data360 API fields: preserve as-is (`OBS_VALUE`, `DATA_SOURCE`, `COMMENT_TS`) since they're passed through to the LLM for citation integrity

**Date/Time:**
- API dates: pass through as-is from Data360 (`TIME_PERIOD` is typically a year string like `"2023"`)
- Internal timestamps: ISO 8601 strings (`"2026-03-23T14:30:00Z"`)

### Process Patterns

**Error Handling:**
- MCP tools: never raise exceptions to the LLM. Always return structured error response (see format above).
- `data360_client.py`: catch httpx exceptions, convert to structured errors with context.
- Log errors with full context (URL, params, status code), return user-safe message in the error response.

```python
# Good: structured error the LLM can narrate
return {"success": False, "error": "No data found for indicator WB_WDI_xxx in BRA", "error_type": "no_data"}

# Bad: raising an exception
raise ValueError("Indicator not found")
```

**Retry Strategy:**
- httpx retry on 429 (rate limit) and 5xx errors only
- Exponential backoff: 1s, 2s, 4s (3 attempts max)
- No retry on 4xx client errors (bad params, not found)

**Logging:**
- Use Python stdlib `logging` module
- Logger per module: `logger = logging.getLogger(__name__)`
- Levels: DEBUG for API request/response details, INFO for tool calls, WARNING for retries/data gaps, ERROR for failures
- No print statements

### Enforcement Guidelines

**All AI Agents MUST:**

1. Use the MCP tool response format (success/error structure) for every tool return
2. Preserve Data360 API field names exactly (`DATA_SOURCE`, `COMMENT_TS`, etc.) in tool responses, never rename them
3. Map Python snake_case params to API UPPERCASE params only inside `data360_client.py`
4. Return structured errors, never raise exceptions from MCP tools
5. Use `logging` module, never `print()`

**Anti-Patterns:**

```python
# WRONG: Renaming API fields
{"data_source": row["DATA_SOURCE"]}  # Don't rename, citation integrity depends on exact field names

# RIGHT: Preserve API field names
{"DATA_SOURCE": row["DATA_SOURCE"]}

# WRONG: Raising exceptions from MCP tools
raise Exception("API failed")

# RIGHT: Returning structured error
return {"success": False, "error": "API failed", "error_type": "api_error"}

# WRONG: Hardcoded values
response = httpx.get("https://data360api.worldbank.org/data360/data")

# RIGHT: Using config
response = await self.client.get(f"{self.base_url}/data360/data", params=params)
```

## Project Structure & Boundaries

### Complete Project Directory Structure

```
data360-voice/
├── pyproject.toml                  # uv project config, dependencies
├── .env.example                    # template for environment variables
├── .gitignore
├── Dockerfile                      # (deferred past Week 1)
├── mcp_server/                     # MCP server (standalone component)
│   ├── __init__.py
│   ├── server.py                   # FastMCP server, 5 tool definitions
│   ├── data360_client.py           # Async World Bank API client
│   └── config.py                   # Base URL, timeouts, pagination limits
├── app/                            # Web application (Week 2+)
│   ├── __init__.py
│   ├── main.py                     # FastAPI app + Chainlit mount
│   ├── chat.py                     # Chainlit handlers (@cl.on_message, etc.)
│   └── config.py                   # App settings (env vars, DB config)
├── .chainlit/                      # (Week 2+)
│   └── config.toml                 # Chainlit configuration
└── tests/
    ├── __init__.py
    ├── mcp_server/
    │   ├── __init__.py
    │   ├── test_server.py          # MCP tool integration tests
    │   ├── test_data360_client.py  # API client unit tests
    │   └── fixtures/               # Sample API responses for testing
    │       ├── searchv2_response.json
    │       ├── data_response.json
    │       └── metadata_response.json
    └── app/                        # (Week 2+)
        ├── __init__.py
        └── test_main.py
```

### Architectural Boundaries

**Boundary 1: MCP Server ↔ World Bank API**
- `data360_client.py` is the ONLY module that makes HTTP calls to `data360api.worldbank.org`
- All 5 tools in `server.py` call through `data360_client.py`, never directly
- Parameter mapping (snake_case → UPPERCASE) happens exclusively in `data360_client.py`
- Retry logic and error wrapping live in `data360_client.py`

```
server.py (tool definitions)
    │ calls
    ▼
data360_client.py (API abstraction)
    │ HTTP calls
    ▼
data360api.worldbank.org
```

**Boundary 2: MCP Server ↔ LLM Client**
- Transport layer (stdio/HTTP Streamable) is handled by FastMCP, not our code
- Tool responses follow the consistent format (success/error structure)
- Data360 API fields (`DATA_SOURCE`, `COMMENT_TS`, etc.) pass through unchanged

**Boundary 3: Web App ↔ MCP Server (Week 2+)**
- Chainlit connects to MCP server as a client (HTTP Streamable)
- MCP server runs as a separate process, not imported directly
- No shared state between web app and MCP server

**Boundary 4: Web App ↔ PostgreSQL (Week 2+)**
- Chainlit-datalayer manages conversation tables (don't touch these)
- Custom cache tables managed by app code in `app/` module
- Single PostgreSQL instance, shared connection pool

### Requirements to Structure Mapping

**FR Category Mapping:**

| FR Category | Primary Location | Key Files |
|------------|-----------------|-----------|
| Data Query & Retrieval (FR1-7) | `mcp_server/` | `server.py` (search_indicators, get_data), `data360_client.py` |
| Citation & Source Attribution (FR8-12) | `mcp_server/` | `data360_client.py` (preserves DATA_SOURCE), `server.py` (response format) |
| Narrative Response Generation (FR13-17) | `app/` | `chat.py` (system prompt with grounding rules) |
| LLM Grounding & Trust (FR18-22) | `app/` | `chat.py` (system prompt constraints) |
| Fact-Check Mode (FR23-26) | `app/` | `chat.py` (prompt engineering for verdict generation) |
| Conversation Management (FR27-30) | `app/` | `main.py` (Chainlit mount), `chat.py` (handlers) |
| MCP Server / Data Integration (FR31-36) | `mcp_server/` | All files |

**Cross-Cutting Concerns Mapping:**

| Concern | Location |
|---------|----------|
| Pagination logic | `mcp_server/data360_client.py` |
| Error handling | `mcp_server/data360_client.py` (API errors), `mcp_server/server.py` (structured responses) |
| Configuration | `mcp_server/config.py`, `app/config.py` (separate per component) |
| Logging | Each module via `logging.getLogger(__name__)` |

### Integration Points

**External Integrations:**

| Integration | Protocol | Module | Auth |
|------------|----------|--------|------|
| World Bank Data360 API | HTTPS (REST) | `mcp_server/data360_client.py` | None (public) |
| Claude API | HTTPS (SSE streaming) | `app/chat.py` | API key (env var) |
| PostgreSQL | TCP (asyncpg) | `app/main.py` | Connection string (env var) |

**Data Flow (End-to-End, Week 2+):**

```
User (browser)
    │ WebSocket (Socket.IO)
    ▼
Chainlit (app/chat.py)
    │ MCP client (HTTP Streamable)
    ▼
MCP Server (mcp_server/server.py)
    │ httpx async
    ▼
data360_client.py
    │ HTTPS
    ▼
data360api.worldbank.org
    │ JSON response (DATA_SOURCE, OBS_VALUE, etc.)
    ▼
(flows back up, fields preserved at each boundary)
```

**Data Flow (Week 1, stdio):**

```
Claude Desktop
    │ stdio (JSON-RPC)
    ▼
MCP Server (mcp_server/server.py)
    │ httpx async
    ▼
data360_client.py
    │ HTTPS
    ▼
data360api.worldbank.org
```

### Development Workflow

**Week 1 (MCP Server only):**
```bash
# Development with Inspector
fastmcp dev mcp_server/server.py

# Install in Claude Desktop for e2e testing
fastmcp install mcp_server/server.py

# Run tests
uv run pytest tests/mcp_server/
```

**Week 2+ (Full App):**
```bash
# Full app development
uvicorn app.main:app --reload

# Or Chainlit directly
chainlit run app/chat.py
```

## Architecture Validation Results

### Coherence Validation

**Decision Compatibility:**
- FastMCP 3.1.1 + Python 3.11+ + httpx: fully compatible, all async-native
- FastMCP handles dual transport (stdio/HTTP Streamable) via config flag, no code changes needed
- Chainlit 2.10.0 mounts in FastAPI 0.135.2 via `mount_chainlit`, confirmed pattern
- PostgreSQL + pgvector + chainlit-datalayer: single database, no conflicts
- No contradictory decisions found

**Pattern Consistency:**
- snake_case naming throughout Python code, UPPERCASE preserved only for Data360 API field passthrough
- Consistent error response format across all 5 MCP tools
- `data360_client.py` as single API boundary is clean and enforced
- Logging pattern (stdlib, per-module logger) is standard and consistent

**Structure Alignment:**
- `mcp_server/` is fully standalone, testable independently via stdio
- `app/` depends on MCP server via MCP client protocol (not import), clean separation
- `tests/` mirrors source structure
- Configuration separated per component (`mcp_server/config.py`, `app/config.py`)

### Requirements Coverage Validation

**Functional Requirements Coverage:**

| FR | Covered By | Status |
|----|-----------|--------|
| FR1-7 (Data Query) | `mcp_server/server.py` (5 tools), `data360_client.py` | Covered |
| FR8-12 (Citations) | DATA_SOURCE passthrough in tool responses, enforcement rules | Covered |
| FR13-17 (Narratives) | `app/chat.py` system prompt design (Week 2+) | Covered |
| FR18-22 (Grounding) | `app/chat.py` system prompt constraints (Week 2+) | Covered |
| FR23-26 (Fact-Check) | `app/chat.py` prompt engineering (Week 2+) | Covered |
| FR27-30 (Conversations) | Chainlit datalayer + PostgreSQL (Week 2+) | Covered |
| FR31-36 (MCP Server) | `mcp_server/` complete architecture | Covered |

**Non-Functional Requirements Coverage:**

| NFR | Covered By | Status |
|-----|-----------|--------|
| NFR1-2 (Latency) | Streaming architecture, caching (deferred) | Covered |
| NFR3 (Concurrency) | Async-native stack (FastAPI, httpx, asyncpg) | Covered |
| NFR4 (Caching) | PostgreSQL cache tables (deferred to Week 2+) | Deferred, acceptable |
| NFR5-8 (Security) | Env vars, HTTPS, no PII | Covered |
| NFR9-12 (Integration) | Error handling patterns, retry strategy, transport-agnostic design | Covered |

### Implementation Readiness Validation

**Decision Completeness:**
- All 5 MCP tool signatures defined with exact parameter types and descriptions
- API parameter mapping documented with official OpenAPI spec as source
- Pagination strategy specified (auto, 1000 increments, 5000 cap)
- Error response format defined with examples

**Structure Completeness:**
- Every file in Week 1 scope has a defined purpose
- Week 2+ files identified but not blocking
- Test fixtures directory specified for deterministic testing

**Pattern Completeness:**
- Anti-patterns documented with "wrong vs right" examples
- 5 enforcement rules clearly stated
- Retry strategy specified (which errors, backoff timing, max attempts)

### Gap Analysis Results

**No Critical Gaps.**

**Important Gaps (non-blocking, address when relevant):**
1. System prompt design for LLM grounding (FR18-22): deferred to Week 2, appropriate since it's an `app/chat.py` concern
2. Caching layer: deferred past Week 1, documented as future work
3. Test fixtures need to be created from real API responses during development

**Nice-to-Have:**
- `get_metadata` tool's OData query syntax could benefit from example queries in the docstring

### Architecture Completeness Checklist

**Requirements Analysis**
- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped

**Architectural Decisions**
- [x] Critical decisions documented with versions
- [x] Technology stack fully specified
- [x] Integration patterns defined
- [x] Performance considerations addressed

**Implementation Patterns**
- [x] Naming conventions established
- [x] Structure patterns defined
- [x] Communication patterns specified
- [x] Process patterns documented

**Project Structure**
- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] Requirements to structure mapping complete

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High

**Key Strengths:**
- MCP server is fully self-contained and testable from day 1
- Official OpenAPI spec used as source of truth for API mapping
- Citation integrity enforced architecturally (DATA_SOURCE passthrough, not feature)
- Clear boundary between Week 1 (MCP server) and Week 2+ (web app)
- Thin wrapper design keeps MCP server simple, reusable, and open-sourceable

**Areas for Future Enhancement:**
- Caching layer (PostgreSQL cache tables, TTL config)
- System prompt design for grounding boundary
- `get_metadata` OData query examples in tool docstring
- Infrastructure & deployment (Docker, Railway/Render)

### Implementation Handoff

**AI Agent Guidelines:**
- Follow all architectural decisions exactly as documented
- Use implementation patterns consistently across all components
- Respect project structure and boundaries
- Refer to this document for all architectural questions
- Preserve Data360 API field names, never rename them

**First Implementation Priority:**
1. `uv init data360-voice && cd data360-voice && uv add fastmcp httpx`
2. Create `mcp_server/config.py` (base URL, timeouts, pagination limits)
3. Create `mcp_server/data360_client.py` (async API client with pagination)
4. Create `mcp_server/server.py` (FastMCP server with 5 tools)
5. Test with `fastmcp dev mcp_server/server.py` (Inspector)
6. Install in Claude Desktop with `fastmcp install mcp_server/server.py`
