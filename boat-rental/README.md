# Anchor & Oar — Boat Rental + MCP

A small boat-rental site you can use two ways:

1. **In a browser** — browse the fleet, pick dates, and book.
2. **From an AI agent** — connect any [Model Context Protocol](https://modelcontextprotocol.io)
   client to the built-in MCP server and rent a boat in natural language.

Both paths share one booking store, so a boat an agent reserves over MCP is
unavailable on the website (and vice-versa) — the calendar can't double-book.

## Stack

- **FastAPI + Jinja2** — website and JSON REST API.
- **MCP Python SDK (`FastMCP`)** — MCP server over the Streamable HTTP
  transport, mounted into the same app at `/mcp`.
- **JSON files** — a read-only boat catalog (`data/boats.json`) and a
  file-backed bookings log (`data/bookings.json`, gitignored). No database.

```
boat-rental/
├── app.py            # FastAPI app: website + REST API; mounts MCP at /mcp
├── mcp_server.py     # FastMCP server; tools wrap store.py
├── store.py          # shared catalog + booking logic (one source of truth)
├── data/boats.json   # the fleet
├── templates/        # index.html, boat.html
└── static/style.css
```

## Run it

```bash
cd boat-rental
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

- Website: <http://localhost:8000>
- REST API: <http://localhost:8000/api/boats>
- MCP endpoint: `http://localhost:8000/mcp`

## MCP tools

| Tool | What it does |
|------|--------------|
| `list_boats` | List the fleet, with optional `location` / `boat_type` / `min_capacity` / `max_price_per_day` filters |
| `get_boat` | Full details for one boat by id |
| `get_quote` | Price specific dates and report availability (no reservation) |
| `book_boat` | Reserve a boat; validates dates, capacity, and conflicts |
| `get_booking` | Look up a booking by id (`bk-xxxxxx`) |
| `cancel_booking` | Cancel a booking and free the dates |

### Connect from Claude Desktop / Claude Code

The server speaks Streamable HTTP. With the app running locally:

**Claude Code**
```bash
claude mcp add --transport http boat-rental http://localhost:8000/mcp
```

**Claude Desktop** (`claude_desktop_config.json`) — desktop expects a stdio
command, so bridge with `mcp-remote`:
```json
{
  "mcpServers": {
    "boat-rental": {
      "command": "npx",
      "args": ["mcp-remote", "http://localhost:8000/mcp"]
    }
  }
}
```

Then ask: *"Find me a sailboat under $600/day and book it for next weekend
under the name Alex Rivera."* The agent will call `list_boats`, `get_quote`,
and `book_boat`.

### Try the MCP endpoint with curl

Streamable HTTP wants both JSON and SSE in the `Accept` header. List the tools:

```bash
curl -s http://localhost:8000/mcp/ \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## REST API

| Method & path | Purpose |
|---|---|
| `GET /api/boats` | List boats (`?location=&type=&min_capacity=&max_price_per_day=`) |
| `GET /api/boats/{id}` | One boat |
| `GET /api/quote?boat_id=&start_date=&end_date=` | Price + availability |
| `POST /api/bookings` | Create a booking (JSON body) |
| `GET /api/bookings/{id}` | Look up a booking |
| `POST /api/bookings/{id}/cancel` | Cancel a booking |
| `GET /api/health` | Health check |

Booking body:
```json
{
  "boat_id": "catalina-30",
  "customer_name": "Alex Rivera",
  "start_date": "2026-07-04",
  "end_date": "2026-07-06",
  "customer_email": "alex@example.com",
  "party_size": 4
}
```

Dates are `YYYY-MM-DD` and **inclusive** — a Fri–Sun charter is 3 days.
