# Task Bus Recovery Procedure

Recovery from a hung `taskbus` MCP server and disconnected `taskbus-bridge`.

## Symptoms

- `taskbus-bridge` logs show `MCP initialize failed: timed out` repeating every 10s for hours.
- `taskbus.service` shows `deactivating (stop-sigterm)` and won't restart.
- `hermes mcp test task-bus` succeeds (fresh connection) but MCP tools return `"MCP server 'task-bus' is not connected"`.
- `ss -tlnp | grep 8765` shows a process holding the port that won't die on SIGTERM.

## Root cause

The `taskbus` MCP server process (uvicorn + FastMCP) gets stuck in its ASGI shutdown handler when systemd sends SIGTERM. The process holds the port open but refuses new connections. The bridge keeps retrying and timing out. The Hermes client's MCP session manager also gets stuck in "unreachable after N consecutive failures" state.

## Recovery steps

### 0. Diagnose: is the MCP server dead or just hung?

```bash
# Check both services
systemctl --user status taskbus          # MCP server
systemctl --user status taskbus-bridge   # bridge (worker loop)
```

- If `taskbus` shows `inactive (dead)` and `taskbus-bridge` shows `active (running)` with timeout errors in its journal, the MCP server died silently (e.g. OOM, crash, or stuck shutdown) while the bridge kept retrying. The bridge does **not** auto-detect that the MCP server is gone — it just keeps timing out.
- If `taskbus` shows `activating (auto-restart)` with `address already in use` errors, a stale process still holds port 8765. See step 1.

### 1. Kill the stuck process

```bash
# Find the PID holding port 8765
ss -tlnp | grep 8765
# Example output: users:(("python",pid=2693,fd=6))

# Force kill
kill -9 2693

# Verify port is free
ss -tlnp | grep 8765  # should return nothing (exit 1)
```

If the PID from `ss` is already dead but port still held, a zombie process inherited the socket. Check `/proc/<pid>/fd/` for socket descriptors. Kill the zombie's parent or the zombie itself.

### 2. Restart the MCP server

```bash
systemctl --user restart taskbus
sleep 3
systemctl --user is-active taskbus  # should be "active"
ss -tlnp | grep 8765                # should show new PID
```

### 3. Restart the bridge

```bash
systemctl --user restart taskbus-bridge
sleep 5
journalctl --user -u taskbus-bridge --since "10 seconds ago" --no-pager | tail -20
```

The bridge should start silently (no error output). If it logs `MCP tools/call HTTP 400: Bad Request`, the MCP server is still degraded — go back to step 1.

### 4. Reset Hermes MCP session state

If MCP tools still return `"MCP server 'task-bus' is not connected"` from within a Hermes session:

```bash
hermes mcp remove task-bus
hermes mcp add task-bus --url http://primary.tail298a48.ts.net:8765/mcp
# Answer Y to "Does this server require authentication?" (no auth needed)
# Answer Y to "Enable all 13 tools?"
```

A new Hermes session is required after re-adding. The old session's MCP session manager is stuck.

### 5. Verify end-to-end

```bash
hermes mcp test task-bus
# Expected: ✓ Connected (Nms), ✓ Tools discovered: 13
```

## Prevention

- The `taskbus.service` systemd unit uses `Restart=on-failure` with a restart counter. After enough failures it enters a restart loop. Monitor with `systemctl --user status taskbus`.
- Consider adding a health check cron job that pings the MCP endpoint and restarts the service if it's unresponsive for >30s.
- The bridge's `_mcp_request` function has a 10s timeout. If the MCP server is alive but slow, the bridge will report "timed out" even though the server is fine. Distinguish between "server hung" (port open, no response) and "server dead" (port closed, connection refused).
