# SSH Delegation to Remote Hermes Agents

Drive Hermes agents on remote machines via Tailscale SSH, without MCP bridges
or relay-based task queues. The primary SSHes into workers and invokes
`hermes chat -z` or `buzz-cli` directly.

## Prerequisites

- Tailscale SSH enabled on all nodes (verified via `tailscale status --json`)
- No SSH key needed — auth is tailnet identity
- Hermes installed on target machine (`~/.local/bin/hermes`)
- `export PATH=$HOME/.local/bin:$PATH` required over non-interactive SSH

## Basic command

```bash
ssh <host>.tail298a48.ts.net 'export PATH=$HOME/.local/bin:$PATH; hermes chat -z "<task>"'
```

## Full PATH for Hermes agents

Non-interactive SSH gets a minimal PATH. Export all bin dirs first:

```bash
ssh <host> 'export PATH=$HOME/.local/bin:$HOME/.bun/bin:$HOME/.cargo/bin:$PATH; hermes ...'
```

## Systemd user services

Raw SSH has no login session, so `systemctl --user` can't find the bus:

```bash
ssh <host> 'export XDG_RUNTIME_DIR=/run/user/1000; systemctl --user status hermes-gateway'
```

## Driving a Hermes agent remotely

Use `hermes chat -Q` to get session ID, then `-r` to continue:

```bash
# Start a session
SESSION=$(ssh <host> 'export PATH=$HOME/.local/bin:$PATH; hermes chat -Q -q "<task>" --max-turns 20' | grep 'session_id:' | awk '{print $2}')

# Continue same session
ssh <host> "export PATH=$HOME/.local/bin:$PATH; hermes chat -Q -r $SESSION -q '<next>'"
```

## Host key verification

`tailscale ssh` resolves via MagicDNS and auto-verifies host keys against the
Tailscale control plane. If `ssh <host>` fails with `Host key verification failed`,
try the FQDN or use `ssh -o StrictHostKeyChecking=accept-new`.

## Port ownership before deploying agent-info on :80

Always check what already owns port 80 before trying to bind it:

```bash
ssh <host> 'ss -tlnp | grep ":80 "'
```

On this network:
- **gen-ai-3090**: Python http.server (its own agent-info) — already on 80
- **primary**: Nextcloud snap apache — removed to free 80
- **nextcloud**: Apache2 (Nextcloud web + agent-info vhost) — keep apache2, stop python fallback
- **ai-agent-4070**: nginx (Archeion proxy + agent-info static) — keep nginx, stop python fallback

## sudo policy per host

| Host | Passwordless sudo? |
|---|---|
| primary | yes |
| nextcloud | yes |
| gen-ai-3090 | **no** (needs interactive terminal) |
| ai-agent-4070 | yes |
| fs | **no** (also no Hermes) |

For passwordless boxes, `ssh host 'sudo ...'` works. For password-locked boxes,
`ssh host 'sudo ...'` fails (no TTY for prompt) — run at an interactive terminal
or use `kill <MainPID>` to trigger `Restart=always` systemd respawn.

## Pitfalls

| Symptom | Cause / Fix |
|---|---|
| `which hermes` → not found | PATH missing `~/.local/bin`. Export it first. |
| `systemctl --user status` → "can't find bus" | `XDG_RUNTIME_DIR` not set. Export `/run/user/$(id -u)`. |
| `ssh host` → `Host key verification failed` | `known_hosts` mismatch or stale. Use FQDN or `accept-new`. |
| `sudo systemctl restart` → "a terminal is required" | Box needs password for sudo. Use `kill <MainPID>` instead. |
| `hermes chat -z` creates a new session every call | `-z` is one-shot only. Use `chat -Q` + `-r` for stateful sessions. |
| `hermes -z ... --continue` silently ignored | `--continue` is a `chat` subcommand flag, not a top-level flag. |
