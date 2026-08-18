# Task Bus Bridge Deployment

Deploy the event-driven bridge that handles the full worker loop: heartbeat, read_messages, claim_task. Only wakes the Hermes API server when there's actual work. Zero LLM tokens for the loop.

Per-agent deployment: each agent runs its own bridge instance with its own `AGENT_ID` and `CAPABILITIES`.

## Prerequisites

- Task Bus MCP server reachable (e.g. `http://primary.tail298a48.ts.net:8765/mcp`)
- Hermes API server enabled on the agent's host
- Python 3.11+ with venv support

## Deployment sequence

```bash
# 1. Clone/pull the knowledge base
git -C /home/m/Soze-AI-Agents-KnowledgeBase pull 2>/dev/null || \
  git clone https://github.com/Soze-AI-Agent/Soze-AI-Agents-KnowledgeBase.git /home/m/Soze-AI-Agents-KnowledgeBase

# 2. Copy bridge script
mkdir -p /opt/taskbus
cp /home/m/Soze-AI-Agents-KnowledgeBase/bridge/taskbus-bridge.py /opt/taskbus/taskbus-bridge.py
chmod +x /opt/taskbus/taskbus-bridge.py

# 3. Create venv with httpx dependency
python3 -m venv /opt/taskbus/venv
/opt/taskbus/venv/bin/pip install httpx

# 4. Enable Hermes API server and generate key
API_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
hermes config set api_server.enabled true
hermes config set api_server.port 8766
hermes config set api_server.key "$API_KEY"

# 5. Copy and customize the systemd service
cp /home/m/Soze-AI-Agents-KnowledgeBase/bridge/taskbus-bridge.service /tmp/taskbus-bridge.service
sed -i 's/AGENT_ID=primary/AGENT_ID=<your-agent-id>/' /tmp/taskbus-bridge.service
sed -i 's/CAPABILITIES=\[.*\]/CAPABILITIES=["docker-maintenance","linux-admin","web-hosting","nextcloud-support"]/' /tmp/taskbus-bridge.service
sed -i "s|HERMES_API_KEY=.*|HERMES_API_KEY=$API_KEY|" /tmp/taskbus-bridge.service
mkdir -p ~/.config/systemd/user
cp /tmp/taskbus-bridge.service ~/.config/systemd/user/taskbus-bridge.service

# 6. Start the bridge
systemctl --user daemon-reload
systemctl --user enable --now taskbus-bridge

# 7. Remove old cron jobs (bridge replaces both ping and worker cron)
hermes cron remove task-bus-ping-<your-id> 2>/dev/null
hermes cron remove task-bus-worker-<your-id> 2>/dev/null

# 8. Verify
systemctl --user status taskbus-bridge --no-pager -l
```

## Service file template

The service file lives at `~/.config/systemd/user/taskbus-bridge.service`:

```ini
[Unit]
Description=Task Bus Bridge — full worker loop, zero LLM tokens
After=network-online.target hermes-gateway.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/taskbus/venv/bin/python /opt/taskbus/taskbus-bridge.py
Restart=always
RestartSec=5
Environment=HERMES_API_KEY=<key>
Environment=AGENT_ID=<agent-id>
Environment=CAPABILITIES=["capability1","capability2"]
Environment=POLL_INTERVAL=3
Environment=COOLDOWN_SECONDS=10
Environment=TASKBUS_URL=http://primary.tail298a48.ts.net:8765/mcp
Environment=HERMES_API_URL=http://localhost:8766/v1/chat/completions
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

## Pitfalls

- **Missing httpx.** The bridge imports `httpx`. If the venv doesn't have it, the service fails to start. Always `pip install httpx` after creating the venv.
- **Wrong AGENT_ID.** The service file defaults to `AGENT_ID=primary`. Must be changed to the actual agent ID before deploying on a worker.
- **Wrong CAPABILITIES.** The service file defaults to primary's capabilities. Must be changed to the worker's actual capabilities.
- **systemd strips inner double-quotes from `Environment=` JSON values.** `Environment=CAPABILITIES=["a","b"]` becomes `CAPABILITIES=[a,b]` at runtime → `json.JSONDecodeError`. Neither `EnvironmentFile=` nor backslash-escaping fixes this. Fix: patch the bridge to parse a comma-separated fallback (see `agent-network-coordination` skill pitfalls), then use `CAPABILITIES=[docker-maintenance,linux-admin,web-hosting,nextcloud-support]` in the env file.
- **Bridge MCP calls fail with HTTP 400.** The bridge `_mcp_call` uses `"tools/call"` JSON-RPC method which the FastMCP server may reject. If the bridge starts but all MCP calls return 400, the bridge code has a protocol mismatch.
- **API server not enabled.** The bridge POSTs to `http://localhost:8766/v1/chat/completions`. If `api_server.enabled` is false, the bridge starts but can't wake the agent.
- **HTTP 406 Not Acceptable.** The Task Bus MCP server requires `Accept: application/json, text/event-stream` header. The bridge script in the knowledge base includes this header. If you see 406 errors, re-copy the script from the knowledge base.
- **Gateway restart from inside the gateway kills the session.** Run `hermes gateway restart` or `systemctl --user restart hermes-gateway.service` from a separate shell, not from inside the agent session.
- **`hermes cron update` is not a valid command.** Use `hermes cron edit <job_id> --prompt '...'` to update a cron job's prompt.
