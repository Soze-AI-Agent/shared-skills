# SQLite Fallback Pattern

When the Task Bus MCP server is unreachable or the bridge is broken, worker cron jobs can fall back to direct SQLite access for heartbeat, message check, and task inspection.

## When to use

- MCP server returns HTTP 400/406/500 errors
- Bridge is down or stuck
- Network to primary.tail298a48.ts.net is unreachable
- Need a quick status check without MCP round-trip

## DB location

```
/opt/taskbus/taskbus.db
```

SQLite WAL mode — concurrent reads OK. Use `python3 -c "import sqlite3; ..."` since `sqlite3` CLI may not be installed.

## Common queries

```python
import sqlite3, json
from datetime import datetime, timezone

conn = sqlite3.connect('/opt/taskbus/taskbus.db')
conn.row_factory = sqlite3.Row
ts = datetime.now(timezone.utc).isoformat()

# Heartbeat
conn.execute('UPDATE workers SET last_heartbeat=?, status="online" WHERE id=?', (ts, worker_id))
conn.execute('INSERT OR IGNORE INTO workers (id, capabilities, status, registered_at, last_heartbeat) VALUES (?,?,?,?,?)',
    (worker_id, json.dumps(capabilities), 'online', ts, ts))
conn.commit()

# Check pending tasks
pending = conn.execute('SELECT COUNT(*) FROM tasks WHERE status="pending"').fetchone()[0]

# Check unread messages
unread = conn.execute('''
    SELECT COUNT(*) FROM messages m
    LEFT JOIN message_reads mr ON mr.message_id=m.id AND mr.agent_id=?
    WHERE (m.recipient=? OR m.recipient='*') AND m.sender!=?
    AND mr.read_at IS NULL
''', (worker_id, worker_id, worker_id)).fetchone()[0]

# Claim a task (use BEGIN IMMEDIATE for atomicity)
conn.isolation_level = None
conn.execute('BEGIN IMMEDIATE')
row = conn.execute('''
    SELECT * FROM tasks WHERE status='pending'
    AND (target_worker IS NULL OR target_worker=?)
    ORDER BY priority DESC, created_at LIMIT 1
''', (worker_id,)).fetchone()
if row:
    conn.execute('UPDATE tasks SET status="claimed", claimed_by=?, claimed_at=?, attempts=attempts+1 WHERE id=?',
        (worker_id, ts, row['id']))
conn.execute('COMMIT')

# Report result
conn.execute('UPDATE tasks SET status="done", result=?, completed_at=? WHERE id=? AND claimed_by=?',
    (json.dumps(result), ts, task_id, worker_id))
conn.commit()
```

## Limitations

- No MCP protocol validation — bypasses server-side checks
- Only works when cron job runs on the same machine as the Task Bus server
- Does not trigger bridge wake-ups (no Hermes API call)
- Must handle `sqlite3` import errors gracefully (not always available in all venvs)
