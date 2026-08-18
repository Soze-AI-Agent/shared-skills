# Stale Worker Reporting Pattern

End-to-end pattern: SQLite stale worker detection → SSE-aware MCP initialize → `send_message` to primary.

## When to use

- Cron job on same host as Task Bus MCP server (has SQLite access)
- Bridge is healthy but cron needs to report stale workers to primary
- No `httpx` or `mcp` library available (stdlib only)

## The pattern

### 1. Check for stale workers via SQLite

```python
import sqlite3, json
from datetime import datetime, timezone

def check_stale_workers(db_path="/opt/taskbus/taskbus.db", threshold_seconds=300):
    """Return list of stale workers (status=online but no heartbeat in threshold)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT id, status, last_heartbeat FROM workers ORDER BY last_heartbeat")
    stale = []
    for r in cur.fetchall():
        w = dict(r)
        if w["status"] == "online":
            hb = datetime.fromisoformat(w["last_heartbeat"])
            age = (datetime.now(timezone.utc) - hb).total_seconds()
            if age > threshold_seconds:
                stale.append({
                    "id": w["id"],
                    "last_heartbeat": w["last_heartbeat"],
                    "stale_seconds": int(age),
                    "stale_days": round(age / 86400, 1)
                })
    conn.close()
    return stale
```

### 2. Initialize MCP session (SSE-aware)

The Task Bus MCP server returns SSE format (`event: message\ndata: {...}\n\n`), not raw JSON. Parse the `data:` line.

```python
import json, urllib.request, uuid

TASKBUS_URL = "http://primary.tail298a48.ts.net:8765/mcp"

def parse_sse(body):
    """Extract first JSON payload from SSE response body."""
    for line in body.decode().split("\r\n"):
        if line.startswith("data: "):
            return json.loads(line[6:])
    return None

def mcp_initialize():
    """Initialize MCP session, return (session_id, result)."""
    req = urllib.request.Request(
        TASKBUS_URL,
        data=json.dumps({
            "jsonrpc": "2.0", "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "worker-cron", "version": "1.0.0"}
            },
            "id": str(uuid.uuid4())
        }).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
    )
    resp = urllib.request.urlopen(req, timeout=10)
    session_id = resp.headers.get("Mcp-Session-Id")
    return session_id, parse_sse(resp.read())
```

### 3. Send message to primary

```python
def mcp_call(session_id, method, params):
    """Call an MCP tool with session header. Returns parsed SSE result."""
    req = urllib.request.Request(
        TASKBUS_URL,
        data=json.dumps({
            "jsonrpc": "2.0", "method": "tools/call",
            "params": {"name": method, "arguments": params},
            "id": str(uuid.uuid4())
        }).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Mcp-Session-Id": session_id
        }
    )
    return parse_sse(urllib.request.urlopen(req, timeout=10).read())

def report_stale_workers(worker_id, stale_workers):
    """Initialize MCP session and send stale worker report to primary."""
    sid, _ = mcp_initialize()
    import time
    time.sleep(0.3)  # brief pause for session propagation

    result = mcp_call(sid, "send_message", {
        "sender": worker_id,
        "recipient": "primary",
        "subject": "stale workers detected",
        "body": json.dumps({
            "stale_workers": stale_workers,
            "note": f"Reported by {worker_id} cron cycle"
        })
    })
    return result
```

### 4. Full tick

```python
def full_tick(worker_id="3090-agent"):
    stale = check_stale_workers()
    if not stale:
        print("No stale workers")
        return

    result = report_stale_workers(worker_id, stale)
    # result["result"]["content"][0]["text"] contains message_id
    msg_id = json.loads(result["result"]["content"][0]["text"]).get("message_id")
    print(f"Reported {len(stale)} stale workers, message_id={msg_id}")
```

## Response structure

`send_message` returns:
```json
{
  "jsonrpc": "2.0",
  "id": "...",
  "result": {
    "content": [{
      "type": "text",
      "text": "{\"message_id\": \"<uuid>\", \"recipient\": \"primary\"}"
    }],
    "isError": false
  }
}
```

The `message_id` is the primary's confirmation — the message was delivered to the bus.

## Pitfalls

- **SSE vs JSON.** The MCP server returns `text/event-stream` content type. `json.loads(resp.read())` fails with `JSONDecodeError: Expecting value: line 1 column 1`. Always parse the `data:` line.
- **Session header case.** The response header is `Mcp-Session-Id` (capital M, capital S). `urllib` headers are case-insensitive, but be consistent.
- **`notifications/initialized` is optional.** The MCP server accepts `tools/call` immediately after `initialize` without the notification. The bridge sends it, but it's not required for basic tool calling.
- **`send_message` to non-existent recipient.** If `recipient` doesn't match a registered agent, the bus still accepts the message but it may never be read. Use `"primary"` for the coordinator.
- **SQLite file permissions.** `/opt/taskbus/taskbus.db` may be owned by a different user. The cron user needs read access. If denied, fall back to MCP `list_workers` tool instead.
