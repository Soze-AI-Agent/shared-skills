# MCP Event Handling: Why Polling Is the Current Default

## Question

Can the primary Hermes agent react to incoming Task Bus events immediately, without polling?

## Answer

Hermes has **no official push-to-wake mechanism for arbitrary MCP server events.** The Hermes MCP client registers tools from a server and uses them during active agent turns. It does not subscribe to server-side SSE events or get woken by them.

## Official options considered

| Approach | Official? | Practical notes |
|---|---|---|
| Hermes cron polling the bus | ✅ Yes | Simple, durable, works now |
| Hermes API server (`POST /v1/runs`) | ✅ Yes | Requires enabling `API_SERVER_ENABLED`; a small bridge listens to Task Bus SSE and calls the API server to start a turn |
| `/api/cron/fire` webhook | ✅ Yes | Good for scheduled/scale-to-zero wake-ups |
| Internal synthetic `MessageEvent` | ⚠️ No | Exists in gateway source (`GatewayRunner._inject_watch_notification`) but is not a stable API |

## Decision

Use a **Hermes cron job** that calls `heartbeat`, `read_messages`, `claim_task`, and `list_workers` every 60 seconds. Revisit an event-driven bridge only if polling becomes a bottleneck.

## Reference pointers

- `gateway/run.py:13050-13090` — internal synthetic event injection (not stable)
- `gateway/platforms/api_server.py:3438-3503` — `/api/cron/fire`
- Hermes docs: `/user-guide/features/mcp`, `/user-guide/features/cron`
