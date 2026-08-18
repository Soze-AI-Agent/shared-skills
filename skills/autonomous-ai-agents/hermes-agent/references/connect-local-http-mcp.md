# Connecting Hermes to a Local HTTP MCP Server

Use this reference when you need to wire the current Hermes instance to an MCP server reachable over HTTP, especially one running on the same host or inside a private network such as Tailscale.

---

## Add the MCP server

Use the Hermes CLI so it discovers tools and writes the correct config shape:

```bash
hermes mcp add <name> --url <endpoint>
```

Example:

```bash
hermes mcp add task-bus --url http://primary.tail298a48.ts.net:8765/mcp
```

When prompted, enable all tools. The CLI writes an entry under `mcp_servers:` in `~/.hermes/config.yaml`.

For an internal server on a trusted network, **do not pass `--auth`**. Adding auth inserts an `Authorization: Bearer ...` header that may break connections when the server expects no auth. If auth is later required, add it explicitly.

Expected config:

```yaml
mcp_servers:
  task-bus:
    url: http://primary.tail298a48.ts.net:8765/mcp
    enabled: true
```

## Test the connection

```bash
hermes mcp test task-bus
hermes mcp list
```

A successful test shows the transport, latency, number of tools, and tool names.

## Restart the gateway

MCP servers are loaded at session/gateway startup. A new session or gateway restart is required for the tools to appear in the active tool list.

**Critical:** do not attempt to restart the gateway from inside a gateway-hosted conversation (e.g. Telegram, Slack, or this CLI session). The gateway kills child shell processes before the restart command can complete. Instead, run the restart from a separate shell or SSH session:

```bash
systemctl --user restart hermes-gateway.service
```

For CLI-only sessions, exit and relaunch Hermes.

## Verify after restart

```bash
hermes mcp list
hermes mcp test task-bus
```

The tools should now be available to the running agent.

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `hermes mcp test` fails with connection error | Confirm the server is running and reachable from this host |
| `406 Not Acceptable` from the server | The endpoint requires proper MCP headers; `hermes mcp test` sends them correctly |
| Tools discovered but not usable in conversation | Gateway/session was not restarted after adding the server |
| `Authorization: Bearer ...` header breaks connection | Remove the `headers:` block from `~/.hermes/config.yaml` if the server expects no auth |
| Gateway restart appears to hang or fails silently | Run it from a separate shell; the current gateway process terminates its own child commands |

---

*Related skill: `devops/agent-network-services` for the Task Bus-specific workflow.*
