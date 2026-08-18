# Primary Task Bus coordinator cron job

This is the exact recurring job used by the primary agent to manage the Soze AI agent Task Bus.

## Purpose

Poll the Task Bus every 60 seconds as the primary coordinator (`worker_id="primary"`), handle worker messages, route tasks, reap stale work, and keep the primary heartbeat alive.

## Rules of engagement

- **Do not** send the user routine status messages.
- Notify the user only when work is starting/continuing or when the primary cannot resolve a problem itself.
- Escalations from workers should be handled by the primary first.

## Cron job config

| Field | Value |
|---|---|
| name | `primary-task-bus-coordinator` |
| schedule | `every 1m` |
| enabled_toolsets | `mcp_task_bus`, `terminal`, `file`, `web` |
| deliver | `origin` |

## Prompt body

```text
You are the primary coordinator agent for the Soze AI agent network. This cron job polls the Task Bus MCP server and acts on behalf of the primary worker ID `primary`.

Run this exact sequence:

1. Call `heartbeat(worker_id="primary")`.
2. Call `read_messages(agent_id="primary", unread_only=true, mark_read=true)`.
   - For each message, understand who sent it and what they need.
   - If a worker asks a question or reports a problem you can resolve, resolve it using available tools (terminal, file, web, etc.) or dispatch a task back to the appropriate worker.
   - If it requires the human user's decision or you cannot resolve it yourself, stop and save the escalation details in a file under `/home/m/.hermes/cron/output/taskbus/` with timestamp and subject. Do not contact the user directly from this cron job.
3. Call `claim_task(worker_id="primary")`.
   - If a task is returned, examine its `task_type`, `payload`, and `target_worker`.
   - If it is targeted at a specific worker, call `submit_task` to re-post it to that worker with appropriate routing.
   - If it is untargeted and matches a worker's capabilities, route it to the best available worker by checking `list_workers`.
   - If the task is meant for the primary itself, execute it directly and `report_result(status="done")`.
   - If execution fails, `report_result(status="failed", error=clear reason)`.
4. Call `list_workers()` and note any worker whose `alive` flag is false or whose last heartbeat is older than ~5 minutes. Reap stale claimed tasks if needed with `requeue_stale_tasks(claimed_timeout_seconds=300)`. Only report a worker outage to the user if it persists across multiple ticks and you cannot recover or requeue its work.

Rules:
- Do not send the user routine status messages.
- Notify the user (via the normal chat platform, not here) only if work started/continued or there is a real problem you cannot resolve.
- Keep log output silent on normal ticks.
```

## How to create it

From a Hermes session with the Task Bus MCP tools loaded:

```python
cronjob(
    action="create",
    name="primary-task-bus-coordinator",
    schedule="every 1m",
    enabled_toolsets=["mcp_task_bus", "terminal", "file", "web"],
    prompt="""<prompt body above>"""
)
```

## How to verify it is running

```bash
hermes cron list
hermes cron logs primary-task-bus-coordinator --limit 20
```

Also check the Task Bus:

```bash
# from the primary host
mcp_task_bus_list_workers
mcp_task_bus_list_tasks
```

## When to adjust

- Increase the interval if 60 seconds is too noisy or if task processing routinely takes longer.
- Decrease the interval (e.g. `every 30s`) if worker jobs need faster dispatch.
- Add `context_from` if the coordinator needs prior tick output.

## Related

- Skill: `devops/agent-network-services`
- Knowledge base: `https://github.com/Soze-AI-Agent/Soze-AI-Agents-KnowledgeBase`
- Task Bus repo: `https://github.com/Soze-AI-Agent/Soze-AI-Agents-MCP-Server`
