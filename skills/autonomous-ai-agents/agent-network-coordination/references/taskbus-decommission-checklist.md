# Task Bus Decommission Checklist

Session: Aug 2026 — User switched from Task Bus interagent comms to a different solution. This checklist captures what was found and how it was cleaned.

## Pre-cleanup state snapshot

- `taskbus-bridge.service` (user) — enabled, running, polling MCP every 3s
- `taskbus.service` (user) — enabled, running on port 8765, healthy (PID 2791)
- `taskbus.service` (system) — enabled, **crash-looping** on same port 8765 (731 restarts)
- `/opt/taskbus/` — server + venv + bridge script + db
- `/home/m/taskbus/` — cloned repo (server, guides, another db)
- `mcp_servers.task-bus` in `~/.hermes/config.yaml`
- Stale cron scripts in `~/.hermes/scripts/`: `3090_worker_tick.py`, `worker-tick-3090.py`, `worker-tick.py`

## Key finding: duplicate systemd units

Both a **user** and **system** `taskbus.service` were installed, fighting over port 8765:
- User instance (PID 2791) bound first → healthy
- System instance (installed by upstream `install.sh`) failed with `Errno 98 address already in use` → auto-restart loop

**Symptom:** `journalctl -u taskbus.service` showed restart counter at 731, `Errno 98` every cycle.
**Fix:** Disable the system duplicate, keep the user instance (or disable both if decommissioning).

## Diagnostic commands

```bash
# Who owns port 8765?
ss -tlnp | grep ':8765 '

# Which systemd units exist?
export XDG_RUNTIME_DIR=/run/user/$(id -u)
systemctl --user list-unit-files | grep taskbus
systemctl list-unit-files | grep taskbus

# Is the process healthy?
ps -o pid,ppid,user,cmd -p <PID>
```

## Removal verified

After cleanup:
- Port 8765 free ✓
- No `taskbus` user/system units ✓
- No `/opt/taskbus` or `/home/m/taskbus` ✓
- No `task-bus` in Hermes config ✓
- Bridge + taskbus services stopped and disabled ✓

## Files that were removed

| File | Original purpose | Why removed |
|---|---|---|
| `/opt/taskbus/` | MCP server + bridge + db | Old comms layer replaced |
| `/home/m/taskbus/` | Cloned upstream repo | Same as above |
| `~/.config/systemd/user/taskbus-bridge.service` | Bridge polling loop | No longer needed |
| `~/.config/systemd/user/taskbus.service` | User MCP server | No longer needed |
| `/etc/systemd/system/taskbus.service` | System MCP server (duplicate) | Was crash-looping |
| `~/.hermes/scripts/3090_worker_tick.py` | Stale worker cron | Not used |
| `~/.hermes/scripts/worker-tick-3090.py` | Stale worker cron | Not used |
| `~/.hermes/scripts/worker-tick.py` | Stale worker cron | Not used |
| `mcp_servers.task-bus` in config.yaml | Hermes MCP entry | Service gone |
