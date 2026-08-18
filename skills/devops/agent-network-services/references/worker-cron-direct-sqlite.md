# Worker cron job: direct SQLite access pattern

When a worker agent runs as a cron job on the **same host** as the Task Bus MCP server, it can bypass the MCP protocol entirely and access the SQLite database directly. This avoids the `initialize` handshake requirement of streamable-http MCP and eliminates `400 Bad Request` errors from raw HTTP calls.

## When to use this pattern

- The worker cron job runs on the same machine as `taskbus.service` (the primary host).
- The worker needs to heartbeat, read messages, and claim tasks.
- The worker does NOT need to call `submit_task` or `send_message` (those require the MCP server to generate UUIDs and enforce consistency — though you can generate UUIDs in Python and INSERT directly).

## When NOT to use this pattern

- The worker runs on a **different host** (remote worker). Must use MCP over Tailscale.
- The worker needs to call `submit_task` or `send_message` — these involve server-side UUID generation and broadcast logic that direct SQLite can replicate but is fragile.

## The pattern

```python
import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = "/opt/taskbus/taskbus.db"
AGENT_ID = "3090-agent"

def now():
    return datetime.now(timezone.utc).isoformat()

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

ts = now()

# 1. Heartbeat
conn.execute(
    "UPDATE workers SET last_heartbeat=?, status='online' WHERE id=?",
    (ts, AGENT_ID)
)

# 2. Read unread messages
cur = conn.execute("""
    SELECT m.* FROM messages m
    LEFT JOIN message_reads mr ON mr.message_id = m.id AND mr.agent_id = ?
    WHERE (m.recipient = ? OR m.recipient = '*')
      AND m.sender != ?
      AND mr.read_at IS NULL
    ORDER BY m.created_at
""", (AGENT_ID, AGENT_ID, AGENT_ID))
messages = cur.fetchall()

# Mark them read
if messages:
    ts2 = now()
    for m in messages:
        conn.execute(
            "INSERT OR IGNORE INTO message_reads (message_id, agent_id, read_at) VALUES (?,?,?)",
            (m['id'], AGENT_ID, ts2)
        )

# 3. Claim a task
cur = conn.execute("""
    SELECT * FROM tasks WHERE status='pending'
    AND (target_worker IS NULL OR target_worker = ?)
    AND type IN ('docker-maintenance','linux-admin','web-hosting','nextcloud-support')
    ORDER BY priority DESC, created_at LIMIT 1
""", (AGENT_ID,))
task = cur.fetchone()

if task:
    tid = task['id']
    conn.execute(
        "UPDATE tasks SET status='claimed', claimed_by=?, claimed_at=?, attempts=attempts+1 WHERE id=?",
        (AGENT_ID, ts, tid)
    )
    # ... do the work ...
    result = {"handled_by": AGENT_ID, "note": "task completed"}
    conn.execute(
        "UPDATE tasks SET status='done', result=?, error=NULL, completed_at=? WHERE id=?",
        (json.dumps(result), now(), tid)
    )

conn.commit()
conn.close()
```

## Advantages over MCP HTTP

| Aspect | MCP HTTP | Direct SQLite |
|---|---|---|
| Protocol | Requires `initialize` handshake before any `tools/call` | None |
| Error modes | `400 Bad Request` if session not initialized | SQL errors only |
| Latency | HTTP round-trip + session management | Local file access |
| Reliability | Depends on server process health | Depends on SQLite WAL |
| Portability | Works from any tailnet host | Same host only |

## Pitfalls

- **SQLite locking**: The Task Bus server uses WAL mode with `busy_timeout=10000`, so concurrent reads are fine. Writes (claim_task, report_result) use `BEGIN IMMEDIATE` in the server — direct SQLite writes should also use `BEGIN IMMEDIATE` or rely on the default deferred locking (which upgrades on write). For cron jobs, the default deferred mode is fine because the write window is small.
- **UUID generation**: The server uses `uuid.uuid4()` for task/message IDs. If you INSERT directly, generate your own UUIDs.
- **Schema changes**: If the server schema changes, direct SQLite access breaks. Keep the schema in sync.
- **Not for remote workers**: Only use on the same host. Remote workers must use MCP over Tailscale.
