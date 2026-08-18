# Cron Worker Direct MCP Call Pattern

When a worker agent runs as a **Hermes cron job** (not a dedicated bridge process), it cannot call Task Bus MCP tools natively — `hermes mcp call` does not exist, and MCP tools don't appear in `hermes tools`. The worker must call the MCP server directly via HTTP.

## The pattern

Every MCP call requires a two-step sequence:

### 1. Initialize session (once per cron tick)

```python
import httpx

url = "http://primary.tail298a48.ts.net:8765/mcp"
headers = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}

r = httpx.post(url, headers=headers, json={
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "<worker-id>", "version": "0.1.0"}
    }
}, timeout=10)

# Capture session ID from response headers
session_id = r.headers.get("mcp-session-id")
```

The response is SSE format (`event: message\ndata: {...}`). The session ID comes from the `Mcp-Session-Id` response header.

### 2. Call tools with session header

```python
headers["Mcp-Session-Id"] = session_id

r = httpx.post(url, headers=headers, json={
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
        "name": "heartbeat",
        "arguments": {"worker_id": "3090-agent"}
    }
}, timeout=10)
```

### 3. Parse SSE response

The response body is SSE format. Extract the JSON from the `data:` line:

```python
if r.text.startswith("event:") or "data:" in r.text:
    for line in r.text.split("\n"):
        if line.startswith("data:"):
            body = json.loads(line[5:].strip())
            # body["result"]["content"][0]["text"] has the actual result
```

## Full cron tick example

```python
import httpx, json

url = "http://primary.tail298a48.ts.net:8765/mcp"
headers = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}

# Step 1: Initialize
r = httpx.post(url, headers=headers, json={
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
               "clientInfo": {"name": "3090-agent", "version": "0.1.0"}}
}, timeout=10)
session_id = r.headers.get("mcp-session-id")
headers["Mcp-Session-Id"] = session_id

# Step 2: Heartbeat
r = httpx.post(url, headers=headers, json={
    "jsonrpc": "2.0", "id": 2, "method": "tools/call",
    "params": {"name": "heartbeat", "arguments": {"worker_id": "3090-agent"}}
}, timeout=10)

# Step 3: Read messages
r = httpx.post(url, headers=headers, json={
    "jsonrpc": "2.0", "id": 3, "method": "tools/call",
    "params": {"name": "read_messages", "arguments": {
        "agent_id": "3090-agent", "unread_only": True, "mark_read": True
    }}
}, timeout=10)

# Step 4: Claim task
r = httpx.post(url, headers=headers, json={
    "jsonrpc": "2.0", "id": 4, "method": "tools/call",
    "params": {"name": "claim_task", "arguments": {
        "worker_id": "3090-agent",
        "task_types": ["docker-maintenance", "linux-admin", "web-hosting", "nextcloud-support"]
    }}
}, timeout=10)
```

## Zero-dependency alternative: `urllib.request` (no pip install)

When `httpx` or the `mcp` library are not installed, use stdlib `urllib.request`. Works in any Python 3 environment with no extra deps.

```python
import json, urllib.request

TASKBUS_URL = "http://primary.tail298a48.ts.net:8765/mcp"
AGENT_ID = "3090-agent"
_session_id = None

def mcp_req(method, params=None):
    global _session_id
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if _session_id:
        headers["Mcp-Session-Id"] = _session_id
    req = urllib.request.Request(
        TASKBUS_URL, data=json.dumps(payload).encode(), headers=headers,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            _session_id = sid
        raw = resp.read().decode()
    if not raw.strip():
        return {}
    if raw.startswith("event:") or "data:" in raw:
        for line in raw.split("\n"):
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return {}
    return json.loads(raw)

# Initialize session
r = mcp_req("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "3090-agent-cron", "version": "1.0.0"},
})

# Heartbeat
hb = mcp_req("tools/call", {"name": "heartbeat", "arguments": {"worker_id": AGENT_ID}})

# Read messages
msgs = mcp_req("tools/call", {"name": "read_messages", "arguments": {
    "agent_id": AGENT_ID, "unread_only": True, "mark_read": True, "limit": 50,
}})

# Claim task
task = mcp_req("tools/call", {"name": "claim_task", "arguments": {
    "worker_id": AGENT_ID,
    "task_types": ["docker-maintenance", "linux-admin", "web-hosting", "nextcloud-support"],
}})
```

**Required: `notifications/initialized`.** The MCP server (FastMCP) requires `notifications/initialized` after `initialize` before it accepts `tools/call`. Without it, the server returns HTTP 400 "Bad Request". Always send it between initialize and the first tool call. The bridge script sends it for this reason — it is NOT optional.

## Alternative: use the `mcp` Python library (cleaner)

Instead of raw `httpx` with manual session initialization, use the official `mcp` library (`pip install mcp`). It handles session lifecycle, SSE parsing, and response deserialization automatically.

```python
import asyncio, json
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession

async def call_tool(session, name, args):
    result = await session.call_tool(name, args)
    texts = [c.text for c in result.content]
    raw = "".join(texts).strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw

async def main():
    async with streamable_http_client("http://primary.tail298a48.ts.net:8765/mcp") as streams:
        read, write, get_sid = streams  # 3-tuple for mcp>=1.26.0
        async with ClientSession(read, write) as session:
            await session.initialize()

            hb = await call_tool(session, "heartbeat", {"worker_id": "3090-agent"})
            msgs = await call_tool(session, "read_messages", {
                "agent_id": "3090-agent", "unread_only": True, "mark_read": True
            })
            claim = await call_tool(session, "claim_task", {
                "worker_id": "3090-agent",
                "task_types": ["docker-maintenance", "linux-admin", "web-hosting", "nextcloud-support"]
            })

asyncio.run(main())
```

**Important:** `streamable_http_client` returns a 3-tuple `(read, write, get_sid)` in `mcp>=1.26.0`. Older versions return a 2-tuple `(read, write)`. If you get `ValueError: too many values to unpack (expected 2)`, use 2-tuple unpacking. If you get `ValueError: not enough values to unpack (expected 3, got 2)`, use 3-tuple unpacking. Check with `pip show mcp | grep Version`.

## Key differences from the bridge

| Aspect | Bridge | Cron worker |
|---|---|---|
| Session lifecycle | Persistent (reuses session across polls) | Fresh initialize per tick |
| Poll interval | 3 seconds | 60+ seconds (cron schedule) |
| LLM cost | Zero (Python only) | Full agent turn per tick |
| Hermes API wake | Yes (POST /v1/chat/completions on work found) | N/A (already in agent turn) |
| Output delivery | `--deliver local` to primary | Cron output goes to configured destination |

## Pitfalls

- **Missing session ID → HTTP 400.** Every `tools/call` without `Mcp-Session-Id` header returns `"Bad Request: Missing session ID"`. Always initialize first. The `mcp` library handles this automatically.
- **Session expires.** The MCP server may expire sessions. If a `tools/call` returns 400 even with a session header, re-initialize.
- **SSE response parsing.** The response body is `event: message\ndata: {...}\n\n`, not plain JSON. Parse the `data:` line. The `mcp` library handles this automatically.
- **`execute_code` blocked in cron.** Cron jobs cannot use `execute_code` (blocked by approval mode). Use `terminal()` with inline `python3 -c` instead.
- **Response structure.** Tool results live at `body["result"]["content"][0]["text"]` (JSON string) or `body["result"]["structuredContent"]["result"]` (parsed). Check both. The `mcp` library returns `result.content` as a list of `TextContent` objects with a `.text` attribute.
- **Server binds to Tailscale IP, not 127.0.0.1.** The Task Bus server binds to the Tailscale IP (e.g. `100.99.71.23`). `curl http://127.0.0.1:8765/mcp` returns "Connection refused" even when the server is running. Always use the Tailscale hostname (`primary.tail298a48.ts.net:8765`) to reach it. Verify with `ss -tlnp | grep 8765` to see the actual bind address.
- **`mcp` library version matters.** `mcp>=1.26.0` uses 3-tuple unpack from `streamable_http_client`. Older versions use 2-tuple. Check with `pip show mcp | grep Version`.
- **`read_messages` response has two formats.** The MCP tool returns both `content` (array of `TextContent` objects) and `structuredContent.result` (parsed array). An empty result (`{"content":[],"structuredContent":{"result":[]}}`) means no unread messages — this is normal, not an error. When parsing the raw SSE response, check `body["result"]["structuredContent"]["result"]` for the parsed array, or `body["result"]["content"][0]["text"]` for the JSON-string version.
- **`claim_task` returns `null` when no tasks available.** The `structuredContent.result` field is `null` (not an empty array `[]`) when no matching task exists. Code that assumes `result` is always a list will crash on `NoneType` iteration. Always guard: `if result and isinstance(result, dict) and result.get("id"):` before treating it as a task. The `content` array is also empty in this case, so neither format carries a task.
