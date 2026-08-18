# Standalone MCP streamable-http calls from Python/curl

When calling Task Bus MCP tools from outside the Hermes MCP client (e.g., a cron job, a Python script, curl), you must complete the `initialize` handshake **before** any `tools/call` request. The streamable-http transport creates a new session per HTTP request; each standalone POST needs its own `initialize` sequence.

## The error

```
400: Bad Request: Missing session ID
```

The server creates a transport session for the request but rejects it because `initialize` was never called on that session.

## Required Accept header

The MCP server requires both `application/json` and `text/event-stream` in the Accept header:

```
Accept: application/json, text/event-stream
Content-Type: application/json
```

Without it you get HTTP 406.

## Full Python pattern

This works for any streamable-http MCP server. The `mcp` Python library handles this automatically — use it when possible:

```python
import asyncio
import json
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession

BASE_URL = "http://primary.tail298a48.ts.net:8765/mcp"

async def call_tool(name, args):
    async with streamable_http_client(BASE_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, args)
            out = []
            for content in result.content:
                if hasattr(content, "text"):
                    out.append(content.text)
            return "".join(out).strip()

result = asyncio.run(call_tool("heartbeat", {"worker_id": "3090-agent"}))
print(json.loads(result))
```

## Pattern for remote workers (different host)

Workers on a different host **must** use MCP over Tailscale — direct SQLite is not available. But they also need the `mcp` Python library installed. The simplest approach:

1. Install the MCP library: `pip install mcp`
2. Use the `streamable_http_client` + `ClientSession` pattern above.
3. The worker's cron job should: initialize → heartbeat → read_messages → claim_task → work → report_result → close.

## Pitfall: streamable-http vs SSE

- **streamable-http**: Each HTTP POST is a fresh session. Must call `initialize` on every request. The `mcp` library handles this transparently.
- **SSE**: One long-lived connection. `initialize` once, then POST `tools/call` to the returned message endpoint. Hermes MCP client also handles this.

## Pitfall: session ID header casing

The MCP server returns the session ID in a **capitalized** `Mcp-Session-Id` response header (capital M, capital S). The `urllib.request` `resp.headers` object handles it case-insensitively per RFC, so `resp.headers.get("mcp-session-id")` also works. For the request header on subsequent `tools/call` calls, use `mcp-session-id` (lowercase) — the server accepts it case-insensitively. **Fix:** Capture the session ID from `resp.headers` immediately after `urlopen`, before reading the body. See `references/worker-cron-urllib-pattern.md` for both variants.

## Pitfall: `urllib.request` vs `http.client` for session management

`urllib.request.urlopen` wraps the response in an `http.client.HTTPResponse` and the `headers` attribute exposes all response headers case-insensitively per RFC. Both `resp.headers.get("Mcp-Session-Id")` and `resp.headers.get("mcp-session-id")` work. The `http.client` module gives you `resp.getheader("mcp-session-id")` directly. Both approaches work; use `urllib.request` for simplicity and `http.client` when you need explicit HTTP status code access during debugging.

## When to use direct SQLite instead

From the **same host** as the Task Bus, direct SQLite access (`/opt/taskbus/taskbus.db`) is simpler and avoids the protocol entirely. See `references/worker-cron-direct-sqlite.md`. Only use the MCP HTTP path when you need `submit_task` or `send_message` (server-side UUID generation), or when running from a different host.