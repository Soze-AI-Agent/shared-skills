# Hermes Agent — reacting to MCP server events

## Research question

Can a Hermes agent be woken up automatically by an event/message from an MCP server (specifically the Task Bus), without polling?

## Method

1. Read the Hermes docs at `https://hermes-agent.nousresearch.com/docs` via the `llms-full.txt` index.
2. Consulted sections: MCP, Use MCP with Hermes, Scheduled Tasks (Cron), Hooks, Gateway internals.
3. Triggered a background subagent to cross-check the `NousResearch/hermes-agent` source if needed.

## Findings

### What Hermes supports officially

- **MCP servers extend the tool set.** They are discovered at startup or via `/reload-mcp`. The agent uses those tools during active turns only.
- **Gateway hooks** are discovered from `~/.hermes/hooks/` (and an empty `gateway/builtin_hooks/` extension point). Events supported:
  - `gateway:startup`
  - `session:start`
  - `session:end`
  - `session:reset`
  - `agent:start`
  - `agent:step`
  - `agent:end`
  - `command:*`
- **Scheduled cron jobs** are the official way to run recurring checks against external systems. Hermes has a `cronjob` tool and a cron subsystem; cron-run sessions get a fresh agent turn.
- **Background maintenance** in the gateway includes cron ticking, session expiry, memory flush, and cache refresh. It does not include reacting to arbitrary external MCP events.

### What Hermes does NOT support

- There is **no hook or API** for an MCP server SSE event to start a new agent turn.
- There is **no documented programmatic way** for an external process to inject a message into the gateway and trigger a session.
- The MCP Python SDK supports SSE push, but Hermes consumes it as a transport for tool calls, not as a wake signal.

## Recommended best practice

Use a **Hermes cron job** that polls the Task Bus every 30–120 seconds:

```text
cronjob(
  action="create",
  name="taskbus-primary-poll",
  schedule="every 60s",
  prompt="As the primary agent, check the Task Bus. Call heartbeat for worker primary, then read_messages for agent_id='primary', then list_tasks for status 'pending' and status 'claimed'. If there are pending tasks, route them. If there are stale claims, call requeue_stale_tasks. If any worker messages need escalation that you cannot resolve yourself, surface them to the user."
)
```

Set `enabled_toolsets=["mcp_task_bus"]` (or whatever toolset name the bus tools are exposed under) to keep the schema small.

## Non-official fallback

If latency requirements exceed what cron allows, a custom background SSE listener could hold the `/sse` connection open and, on a relevant event, invoke `hermes` CLI or call an internal Hermes API. Hermes does **not** document a stable API for this, so this path is bespoke and may break with updates. The official recommendation is to use cron.

### Source excerpts

From `llms-full.txt` (Hermes docs):

> MCP lets Hermes Agent connect to external tool servers so the agent can use tools that live outside Hermes itself… Automatic tool discovery and registration at startup.

> Schedule tasks to run automatically with natural language or cron expressions. Hermes exposes cron management through a single `cronjob` tool.

> Gateway hooks are Python modules that respond to lifecycle events: `gateway:startup`, `session:start`, `session:end`, `session:reset`, `agent:start`, `agent:step`, `agent:end`, `command:*`.

> The gateway runs periodic maintenance alongside message handling: Cron ticking, Session expiry, Memory flush, Cache refresh.

### Deep source check (via subagent)

A background subagent also inspected the `NousResearch/hermes-agent` source:

- `gateway/run.py:7248-7350` — `_handle_message()` and `pre_gateway_dispatch` hook.
- `gateway/run.py:13050-13090` — `_inject_watch_notification()` uses an internal synthetic `MessageEvent`.
- `gateway/run.py:5199-5269` — `_schedule_resume_pending_sessions()` resumes sessions with synthetic events.
- `gateway/platforms/base.py:4145` — `BasePlatformAdapter.handle_message()` spawns agent turns.
- `gateway/platforms/api_server.py:3438-3503` — `POST /api/cron/fire` handler (authenticated webhook).
- `hermes_cli/plugins.py:128-200` — `VALID_HOOKS`.

Findings from source:
- The **only documented push surfaces** are the API server endpoints (`POST /v1/chat/completions`, `/v1/runs`) and the **Chronos `/api/cron/fire` webhook**.
- The synthetic `MessageEvent` injection path is **internal implementation**, not a stable public API.
- There is no first-class “MCP event listener” or “gateway hook” for arbitrary MCP server events.

## Conclusion

For the Soze AI agent network, the primary agent should react to Task Bus activity via a scheduled poll, not a real-time event listener. The user explicitly wants the primary to manage the bus autonomously and only escalate unresolved issues.

If future latency requirements demand push, the least-unsupported path is to run a tiny bridge that receives Task Bus SSE events and calls `POST /v1/runs` on the Hermes API server (or `POST /api/cron/fire`). This is still bespoke infrastructure and should be revisited only if cron proves insufficient.

