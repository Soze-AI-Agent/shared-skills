# Worker cron job: MCP library pattern (remote host)

When a worker agent runs as a cron job on a **different host** from the Task Bus MCP server, it must use the MCP streamable-http protocol over Tailscale. Use the `mcp` Python library — it handles the `initialize` handshake and session management transparently.

## When to use

- Worker runs on a different machine than `taskbus.service`.
- Worker needs heartbeat, read_messages, claim_task, report_result.
- Worker may also need submit_task (to route work to another worker) or send_message.

## When NOT to use

- Worker runs on the **same host** as the Task Bus. Use direct SQLite instead (`references/worker-cron-direct-sqlite.md`).

## Full worker cron loop

```python
#!/usr/bin/env python3
import asyncio
import json
from datetime import datetime, timezone
from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession

BASE_URL = "http://primary.tail298a48.ts.net:8765/mcp"
WORKER_ID = "3090-agent"
TASK_TYPES = ["docker-maintenance", "linux-admin", "web-hosting", "nextcloud-support"]

async def call_tool(session, name, args):
    try:
        result = await session.call_tool(name, args)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    out = []
    for content in result.content:
        if hasattr(content, "text"):
            out.append(content.text)
    text = "".join(out).strip()
    if not text:
        return {"ok": True, "result": None}
    try:
        return {"ok": True, "result": json.loads(text)}
    except json.JSONDecodeError:
        return {"ok": True, "result": text}

async def main():
    async with streamable_http_client(BASE_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. Heartbeat
            hb = await call_tool(session, "heartbeat", {"worker_id": WORKER_ID})
            if not hb["ok"]:
                print("heartbeat failed:", hb["error"])
                return
            known = hb["result"].get("known", False)
            if not known:
                reg = await call_tool(session, "register_worker", {
                    "worker_id": WORKER_ID,
                    "capabilities": TASK_TYPES,
                })
                print("registered:", json.dumps(reg.get("result")))

            # 2. Read messages
            msgs = await call_tool(session, "read_messages", {
                "agent_id": WORKER_ID, "unread_only": True, "mark_read": True,
            })
            messages = msgs.get("result") or []
            if isinstance(messages, dict):
                messages = [messages]

            # Handle or escalate each message
            for msg in messages:
                sender = msg.get("sender", "unknown")
                subject = msg.get("subject", "(no subject)")
                body = msg.get("body", "")
                # If resolvable, handle. Otherwise escalate to primary.
                # Escalate: send_message(sender="3090-agent", recipient="primary", ...)

            # 3. Claim task
            claim = await call_tool(session, "claim_task", {
                "worker_id": WORKER_ID,
                "task_types": TASK_TYPES,
            })
            task = claim.get("result")
            if task:
                tid = task["id"]
                ttype = task.get("type") or task.get("task_type")
                payload = task.get("payload", {})
                # ... execute the work ...
                result = {"handled_by": WORKER_ID, "type": ttype}
                await call_tool(session, "report_result", {
                    "task_id": tid,
                    "worker_id": WORKER_ID,
                    "status": "done",
                    "result": result,
                })

if __name__ == "__main__":
    asyncio.run(main())
```

## Prerequisites

```bash
pip install mcp
```

The `mcp` package provides `streamable_http_client` and `ClientSession`. Install it in the worker's Python environment (venv or system).

## Protocol details

The streamable-http transport creates a new session per HTTP request. The `mcp` library handles this transparently:

1. `streamable_http_client(url)` opens a connection.
2. `ClientSession(read, write)` wraps it.
3. `session.initialize()` sends the MCP `initialize` handshake.
4. Subsequent `session.call_tool(...)` calls include the session ID in headers.
5. On `__aexit__`, the session is closed.

You do NOT need to manage session IDs manually — the library does it.

## Error handling

| Error | Cause | Fix |
|---|---|---|
| `400 Bad Request: Missing session ID` | Called `tools/call` without `initialize` | Use the `mcp` library (handles this) |
| `406 Not Acceptable` | Missing `text/event-stream` in Accept header | The `mcp` library sets correct headers |
| Connection refused | MCP server down | Check `systemctl --user status taskbus` on primary |
| `known: false` on heartbeat | Worker never registered | Call `register_worker` once, or heartbeat auto-registers? No — heartbeat only updates existing rows. Must register first. |

## `[SILENT]` pattern

When the worker cron job finds **no tasks, no messages, and no problems**, return `[SILENT]` as the final response. This suppresses delivery to the user. Only produce a real report when there is actual work or a problem to report.

## See also

- `references/worker-cron-direct-sqlite.md` — same-host alternative (simpler, no MCP protocol)
- `references/standalone-mcp-http-calls.md` — raw HTTP approach (for debugging)
- `references/primary-taskbus-cronjob.md` — primary coordinator cron job
