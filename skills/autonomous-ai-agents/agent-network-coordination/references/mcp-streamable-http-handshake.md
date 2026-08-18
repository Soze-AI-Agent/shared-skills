# MCP Streamable-HTTP Handshake Pattern

The Task Bus MCP server uses `streamable-http` transport (FastMCP). Direct JSON-RPC `tools/call` without a prior `initialize` handshake returns HTTP 400 "Missing session ID".

## Required sequence

```
1. POST /mcp  →  initialize  →  capture Mcp-Session-Id from response headers
2. POST /mcp  →  tools/call  →  include Mcp-Session-Id header
```

## Step 1: Initialize

```python
import urllib.request, json

url = "http://primary.tail298a48.ts.net:8765/mcp"
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream"
}

init_payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "my-agent", "version": "1.0.0"}
    }
}

req = urllib.request.Request(url, data=json.dumps(init_payload).encode(), headers=headers)
with urllib.request.urlopen(req, timeout=5) as resp:
    session_id = resp.headers.get("Mcp-Session-Id")
    body = resp.read().decode()
    # body is SSE format: "event: message\ndata: {...}\n\n"
```

## Step 2: tools/call with session

```python
headers_with_session = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "Mcp-Session-Id": session_id
}

call_payload = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
        "name": "heartbeat",
        "arguments": {"worker_id": "3090-agent"}
    }
}

req = urllib.request.Request(url, data=json.dumps(call_payload).encode(), headers=headers_with_session)
with urllib.request.urlopen(req, timeout=5) as resp:
    result = resp.read().decode()
    # result is SSE format: "event: message\ndata: {\"jsonrpc\":\"2.0\",\"id\":2,\"result\":{...}}\n\n"
```

## Response format

All responses are SSE (Server-Sent Events) format, even for `tools/call`:

```
event: message
data: {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"{...}"}],"isError":false}}

```

Parse by extracting the `data:` line and JSON-parsing it.

## Key details

- **Accept header is mandatory.** The server rejects requests without `application/json, text/event-stream` (HTTP 406 Not Acceptable). This applies to both `initialize` and `tools/call` requests. Always include this header.
- **Session ID is per-initialize.** Each `initialize` creates a new session. Sessions are not persistent across connections.
- **SSE response body.** Even `tools/call` returns SSE-formatted text, not plain JSON. The `data:` line contains the JSON-RPC response.
- **No session needed for SSE transport.** The `/sse` endpoint creates a persistent connection with automatic session management. Use SSE if you want to avoid the handshake dance.
- **`tools/list` also requires a session.** Same handshake pattern as `tools/call`.
