# Task Bus Bridge — Full Worker Loop

Event-driven bridge that handles the complete worker loop: heartbeat, read_messages, claim_task. Only wakes the Hermes API server when there's actual work. Zero LLM tokens for the loop.

## How it works

1. Polls Task Bus every 3 seconds via MCP JSON-RPC
2. Each poll: heartbeat → read_messages → claim_task
3. Hashes current state (message IDs, claimed task ID)
4. On state change → `POST /v1/chat/completions` to Hermes API server
5. 10-second cooldown between wake-ups
6. Fire-and-forget — doesn't wait for agent response

## Per-agent deployment

Each agent (primary + every worker) runs its own bridge instance with its own `AGENT_ID` and `CAPABILITIES`. The bridge only watches for events relevant to that agent.

## Prerequisites

1. Hermes API server enabled on the agent's host:
   ```bash
   hermes config set api_server.enabled true
   hermes config set api_server.key "$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
   hermes config set api_server.port 8766
   hermes gateway restart  # from outside the gateway
   ```

2. Task Bus MCP server reachable (already configured for network agents)

3. Python venv with httpx:
   ```bash
   python3 -m venv /opt/taskbus/venv
   /opt/taskbus/venv/bin/pip install httpx
   ```

## Install

```bash
# Copy the bridge script
cp Soze-AI-Agents-KnowledgeBase/bridge/taskbus-bridge.py /opt/taskbus/taskbus-bridge.py
chmod +x /opt/taskbus/taskbus-bridge.py

# Create systemd service (edit AGENT_ID, CAPABILITIES, and HERMES_API_KEY)
cat > ~/.config/systemd/user/taskbus-bridge.service << 'EOF'
[Unit]
Description=Task Bus Bridge — full worker loop, zero LLM tokens
After=network-online.target hermes-gateway.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/taskbus/venv/bin/python /opt/taskbus/taskbus-bridge.py
Restart=always
RestartSec=5
Environment=HERMES_API_KEY=<your-api-key>
Environment=AGENT_ID=<your-worker-id>
Environment=CAPABILITIES=["docker-maintenance","linux-admin"]
Environment=POLL_INTERVAL=3
Environment=COOLDOWN_SECONDS=10
Environment=TASKBUS_URL=http://primary.tail298a48.ts.net:8765/mcp
Environment=HERMES_API_URL=http://localhost:8766/v1/chat/completions
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now taskbus-bridge
```

## Remove old cron jobs

The bridge replaces both the 5-minute ping and the 15-minute worker cron:

```bash
hermes cron remove task-bus-ping-<your-id> 2>/dev/null
hermes cron remove task-bus-worker-<your-id> 2>/dev/null
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `TASKBUS_URL` | `http://primary.tail298a48.ts.net:8765/mcp` | Task Bus MCP endpoint |
| `HERMES_API_URL` | `http://localhost:8766/v1/chat/completions` | Hermes API server |
| `HERMES_API_KEY` | (required) | API server key |
| `AGENT_ID` | `primary` | This agent's worker ID |
| `CAPABILITIES` | `[]` | JSON array of task types this agent handles |
| `POLL_INTERVAL` | `3` | Seconds between polls |
| `COOLDOWN_SECONDS` | `10` | Minimum seconds between wake-ups |

## Verify

```bash
systemctl --user status taskbus-bridge
journalctl --user -u taskbus-bridge -f
```

Expected log output:
```
taskbus-bridge starting: agent=<your-id>, poll=3s
```

## Troubleshooting

### HTTP 406 Not Acceptable

The bridge sends `Accept: application/json, text/event-stream` header. If you see 406 errors, the bridge script may be outdated. Re-copy from the knowledge base.

### API server not reachable

The Hermes API server starts as part of the gateway. If `curl http://localhost:8766/health` fails, the gateway needs a restart from outside the agent session.

### Bridge won't start

Check logs: `journalctl --user -u taskbus-bridge -n 20 --no-pager`

Common causes:
- `AGENT_ID` not set in service file
- `CAPABILITIES` not set or wrong format — systemd strips inner double-quotes from `Environment=` JSON values. Use comma-separated format in env file: `CAPABILITIES=[docker-maintenance,linux-admin]` and patch bridge to parse fallback.
- `HERMES_API_KEY` not set or wrong
- Task Bus URL unreachable (Tailscale issue)
- Missing httpx in venv

### All MCP calls return HTTP 400

Bridge starts (logs show `taskbus-bridge starting: agent=...`) but every MCP call fails with HTTP 400. The bridge `_mcp_call` uses JSON-RPC method `"tools/call"` which the FastMCP server may reject. Check the server's expected method format and patch the bridge's payload accordingly.
