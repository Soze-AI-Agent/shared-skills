# Task Bus — Common Lifecycle Patterns

Reference for the primary coordinator when dispatching work, tracking completion, and handling stale workers.

## Submit a task to one worker

**CRITICAL: use `action: "shell"` in the payload.** Workers reject `action: "linux-admin"` and `action: "run_commands"`. Only `"shell"` is accepted. If you don't know what action value a worker accepts, use the action-value probe pattern below.

```python
submit_task(
    task_type="linux-admin",
    target_worker="3090-agent",
    priority=2,
    payload={
        "action": "shell",
        "commands": ["command1", "command2"],
        "task_name": "do-something"
    }
)
```

### Action-value probe pattern

When a worker rejects tasks with `"unrecognized linux-admin action: <value>"`, discover what it accepts:

1. Submit a probe task with `action: "shell"` and a command that echoes accepted values:
   ```python
   submit_task(
       task_type="linux-admin",
       target_worker="<worker-id>",
       priority=5,
       max_retries=2,
       payload={
           "action": "shell",
           "commands": ["echo 'ACTION_VALUES_ACCEPTED: shell run execute command script'"],
           "task_name": "action-value-query"
       }
   )
   ```
2. If it succeeds, the worker accepts `"shell"`. If it fails with a different error, the error message will tell you what it expects.
3. Once you know the accepted action value, use it for all future tasks to that worker.

## Submit a task to any available worker

```python
submit_task(
    task_type="linux-admin",
    target_worker=None,
    priority=2,
    payload={"...")
}
```

## Track task status

```python
list_tasks(status="pending")
list_tasks(status="claimed")
list_tasks(status="done")
get_task(task_id="...")
```

## Check worker liveness

```python
list_workers(stale_after_seconds=300)
```

A worker is flagged `alive: true` if it heartbeated inside the threshold.

## Reap stale claimed tasks

```python
requeue_stale_tasks(claimed_timeout_seconds=300)
```

## Notify a worker

```python
send_message(
    recipient="3090-agent",
    sender="primary",
    subject="heads-up",
    body="..."
)
```

## Common failure patterns

| Symptom | Likely cause | Fix |
|---|---|---|
| Worker claims task but result is `unknown_task_type` | Worker doesn't know how to handle the `task_type` | Use `linux-admin` or another generic type with explicit `commands` |
| Install task says "restart_needed" but not done | Gateway cannot restart itself from inside | Send a message instructing external restart via `systemctl --user restart hermes-gateway.service` |
| Worker is `alive: false` | Missed heartbeats | Wait for it to come back; reap if it holds a claimed task |
| Task stuck in `claimed` | Worker died mid-task | Call `requeue_stale_tasks` |
| Worker cron spamming user's Telegram | `deliver=origin` instead of `local` | Fix with `hermes cron edit <job-id> --deliver local` |

## Rollout pattern

For a network-wide config change:

1. Push change to knowledge base repo.
2. Submit install/apply task to each relevant worker with `target_worker`.
3. Use `action: "shell"` in the payload — workers reject other action values.
4. Schedule a one-time cron job to check completion in ~20 minutes.
5. Report done/blocked list to user, not per-worker noise.

## Duplicate task cleanup

When a worker is slow to respond (15-min cycle), do NOT resubmit the same task. Duplicates clog the queue. If duplicates already exist:

```python
# List all pending tasks for a worker
list_tasks(status="pending", target_worker="<worker-id>")

# Delete duplicates directly from the SQLite DB, keeping only the newest of each type
# Path: /opt/taskbus/taskbus.db
# DELETE FROM tasks WHERE id IN (<duplicate-ids>)
```

## Cron delivery fix

Worker cron jobs that spam the user's Telegram have `deliver=origin`. Fix:

```bash
hermes cron edit <job-id> --deliver local
```

All worker cron jobs should use `--deliver local` so output goes to the primary, not the end user.

## `hermes cron update` does not exist

The correct command to update a cron job's prompt or schedule is:

```bash
hermes cron edit <job-id> --prompt '...'
hermes cron edit <job-id> --schedule 'every 15m'
```

Do NOT use `hermes cron update` — it is not a valid command. Task payloads that include `hermes cron update` will fail.

## Bridge-only pattern (current)

The Task Bus Bridge now handles the full worker loop. No cron jobs needed. The bridge does heartbeat, read_messages, and claim_task every 3 seconds. Only wakes the agent when there's actual work.

When submitting tasks to a bridge-equipped worker, the worker will claim the task on its next 3-second poll and the bridge will wake the agent to process it. No need to wait for a 15-minute cron cycle.
