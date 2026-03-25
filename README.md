# Data360 Voice

A conversational AI tool that lets you query World Bank climate and development data using natural language, with verified citations. Powered by the [World Bank Data360 API](https://data360api.worldbank.org) and exposed as an MCP server for use with Claude Desktop or any MCP-compatible client.

No API keys required — Data360 is a public API.


## What It Does

Data360 Voice gives Claude (or any MCP client) five tools to interact with World Bank data:

| Tool | Description |
|---|---|
| `search_indicators` | Full-text search across thousands of indicators |
| `get_data` | Retrieve time-series data for an indicator by country and year range |
| `get_metadata` | Query detailed metadata about indicators, datasets, and topics |
| `list_indicators` | List all indicators available in a given dataset |
| `get_disaggregation` | Get available disaggregation dimensions for a dataset or indicator |

Responses from the `get_data` tool include citation fields (`DATA_SOURCE` / `CITATION_SOURCE`) so Claude can ground answers in verifiable sources. Other tools return raw API data that may not include these fields.


## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)
- Claude Desktop (for desktop integration)


## Installation

```bash
git clone https://github.com/felipetio/data360-voice
cd data360-voice
uv sync
```


## Connect to Claude Desktop

### Option 1 — Automatic install (recommended)

Run this once from the project directory:

```bash
uv run fastmcp install claude-desktop mcp_server/server.py --name "Data360 Voice" --with-editable .
```

This writes the server config to Claude Desktop's config file automatically. Then:

1. Restart Claude Desktop
2. Look for the tools icon (hammer) in the chat input area
3. You should see 5 tools listed under "Data360 Voice"

### Option 2 — Manual config

If you prefer to configure Claude Desktop manually, add the following entry to your Claude Desktop config file:

**Config file location:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "Data360 Voice": {
      "command": "/absolute/path/to/data360-voice/.venv/bin/fastmcp",
      "args": [
        "run",
        "/absolute/path/to/data360-voice/mcp_server/server.py"
      ],
      "env": {}
    }
  }
}
```

Replace `/absolute/path/to/data360-voice` with the actual path on your machine. Then restart Claude Desktop.

### Verifying the connection

Open Claude Desktop and ask:

> "Search for CO2 emissions indicators using the Data360 tools"

Claude should call `search_indicators` and return a list of matching indicators with their dataset IDs.


## Running Locally (without Claude Desktop)

### MCP Inspector (browser-based tool testing)

```bash
uv run fastmcp dev mcp_server/server.py
```

Opens a browser UI where you can call each tool directly and inspect responses.

### HTTP Streamable mode

```bash
MCP_TRANSPORT=streamable-http uv run python -m mcp_server.server
```

Starts an HTTP server at `http://127.0.0.1:8000/mcp`. Any MCP-compatible client can connect to this endpoint.


## Configuration

All settings are optional — defaults work out of the box.

| Environment Variable | Default | Description |
|---|---|---|
| `DATA360_BASE_URL` | `https://data360api.worldbank.org` | API base URL |
| `DATA360_REQUEST_TIMEOUT` | `30.0` | HTTP timeout in seconds |
| `DATA360_MAX_RETRIES` | `3` | Retry attempts on 429/5xx errors |
| `DATA360_RETRY_BACKOFF_BASE` | `1.0` | Exponential backoff base (seconds) |
| `MCP_TRANSPORT` | `stdio` | Transport mode (`stdio` or `streamable-http`) |

You can set these in a `.env` file in the project root.


## Running Tests

```bash
uv run python -m pytest
```


## Architecture

```
mcp_server/
  config.py          # ENV-based config
  data360_client.py  # Async httpx client (retry, pagination, citation enrichment)
  server.py          # FastMCP server + tool definitions
tests/
  mcp_server/        # Unit and integration tests
```

Data flow: `World Bank Data360 API -> Data360Client -> MCP tools -> Claude Desktop`
