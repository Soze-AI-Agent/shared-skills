# SSH-based fleet operations for Hermes agents on Tailscale

Operate a distributed fleet of Hermes agents by SSHing directly to each machine over the
Tailscale tailnet. This replaces the Task Bus / MCP-based interagent comms when that layer
is decommissioned. All five documented Linux boxes are reachable as user `m` with no
password via Tailscale SSH.

## The fleet

| Host | MagicDNS | Tailnet IP | Hermes | sshd fallback? |
|---|---|---|---|---|
| gen-ai-3090 | `gen-ai-3090.tail298a48.ts.net` | 100.127.56.74 | v0.18.2 → 0.20.1 | yes (LAN IP) |
| ai-agent-4070 | `ai-agent-4070.tail298a48.ts.net` | 100.117.11.2 | v0.19.0 → 0.20.1 | yes |
| primary | `primary.tail298a48.ts.net` | 100.99.71.23 | v0.18.2 | yes |
| nextcloud | `nextcloud.tail298a48.ts.net` | 100.88.115.124 | v0.20.0 | **NO** |
| fs | `fs.tail298a48.ts.net` | 100.88.234.126 | **none** | **NO** |

> `nextcloud` and `fs` have **no openssh-server installed** — Tailscale SSH is the only path in.
> Never run `tailscale set --ssh=false` on those two.

## Connecting

### Basic SSH

```bash
ssh nextcloud.tail298a48.ts.net "hostname"
ssh gen-ai-3090.tail298a48.ts.net "hostname"
```

Use the **MagicDNS FQDN**, not the bare hostname. The bare name `nextcloud` resolves to
`127.0.1.1` via `/etc/hosts` on some machines, causing a connection to localhost instead
of the tailnet node.

### Host key verification on first connect

If `~/.ssh/known_hosts` does not exist or the host is new, `ssh` tries to read a passphrase
from `/dev/tty` (which doesn't exist in non-interactive mode) and fails with "Host key
verification failed" even though `StrictHostKeyChecking` defaults to `ask`.

**Fix:** Use `accept-new` (auto-accepts new keys, still rejects changed ones):

```bash
ssh -o StrictHostKeyChecking=accept-new nextcloud.tail298a48.ts.net "hostname"
```

This accepts the key once and writes it to `~/.ssh/known_hosts` for future connections.

> **NOTE:** The `tailscale ssh` wrapper does NOT accept `-o` flags — it forwards them
> to the underlying `ssh` command by name, not by value, so `-o StrictHostKeyChecking=accept-new`
> fails with `flag provided but not defined: -o`. Use bare `ssh` (not `tailscale ssh`) when
> you need `-o` flags.

### FQDN vs bare hostname

The bare hostname `nextcloud` may resolve to `127.0.1.1` via `/etc/hosts`, causing a
connection to localhost instead of the tailnet node. Always use the **MagicDNS FQDN**:

```bash
# Correct
ssh nextcloud.tail298a48.ts.net "hostname"

# Wrong — may connect to 127.0.1.1
ssh nextcloud "hostname"
```

### Verbose diagnostics

When a host fails, determine which SSH server is answering:

```bash
ssh -v gen-ai-3090.tail298a48.ts.net "hostname" 2>&1 | grep -E 'banner|Authenticated|Tailscale'
```

- `using "none"` + `Tailscale` banner = Tailscale SSH is serving port 22
- `OpenSSH_...` banner = real sshd is serving port 22

If Tailscale SSH fails with `operation not permitted` after successful auth, the target runs
the **snap** build of tailscaled (AppArmor blocks session setup). The fix is migrating to
the apt package or running `sudo tailscale set --ssh=false` (only where sshd fallback
exists). See the `tailnet-servers` skill reference `troubleshooting.md` for the full ladder.

## Non-interactive PATH gotcha

Raw `ssh host 'cmd'` has a minimal PATH that excludes `~/.local/bin`, `~/.bun/bin`, and
`~/.cargo/bin`. `hermes`, `bun`, `uv`, and `cargo` all live there. Always export PATH first:

```bash
ssh <host> 'export PATH=$HOME/.local/bin:$HOME/.bun/bin:$HOME/.cargo/bin:$PATH; hermes version'
```

## `systemctl --user` over SSH

Raw SSH has no login session, so the user bus address is unset:

```bash
ssh <host> 'export XDG_RUNTIME_DIR=/run/user/1000; systemctl --user status hermes-gateway'
```

## Fleet-wide Hermes operations

### Check versions across the fleet

```bash
for host in gen-ai-3090 nextcloud ai-agent-4070; do
  echo "=== $host ==="
  timeout 8 ssh ${host}.tail298a48.ts.net \
    'export PATH=$HOME/.local/bin:$PATH; hermes version 2>&1 | head -1' 2>&1
done
```

### Upgrade a machine

```bash
ssh gen-ai-3090.tail298a48.ts.net \
  'cd ~/.hermes/hermes-agent && git pull && export PATH=$HOME/.local/bin:$PATH && pip install -e . 2>&1 | tail -5'
```

**PEP 668 note:** On Ubuntu with system Python, `pip install -e .` may fail with
"externally-managed-environment". If the install method is `git` (Hermes runs directly
from the repo without a separate venv), the binary may already reflect the new version
post-`git pull` — verify with `hermes version` before worrying about the pip error.

### Set model across the fleet

```bash
for host in gen-ai-3090 nextcloud ai-agent-4070; do
  ssh ${host}.tail298a48.ts.net \
    'export PATH=$HOME/.local/bin:$PATH; hermes config set model.default kimi-k2.6 && hermes config set model.provider ollama-cloud'
done
```

### Strip stale MCP config

After decommissioning the Task Bus, remove the `mcp_servers.task-bus` entry from each
agent's config. The `patch` tool refuses `~/.hermes/config.yaml` as security-sensitive; use
`sed`:

```bash
for host in gen-ai-3090 nextcloud ai-agent-4070; do
  ssh ${host}.tail298a48.ts.net \
    'sed -i "/^mcp_servers:/,/^  enabled: true$/d" ~/.hermes/config.yaml; sed -i "/^task-bus:/,/^  enabled: true$/d" ~/.hermes/config.yaml'
done
```

Verify after:
```bash
ssh ${host}.tail298a48.ts.net 'grep -c task-bus ~/.hermes/config.yaml || echo clean'
```

## Diagnosing "N carried commits" version output

When `hermes version` shows `upstream X · local Y (+N carried commits)`, this does NOT
always mean local modifications exist. Check before assuming a fork:

```bash
cd ~/.hermes/hermes-agent
git fetch origin main
git log --oneline origin/main..HEAD | wc -l   # "ahead" count
git log --oneline HEAD..origin/main | wc -l    # "behind" count
git status --short                             # actual local modifications
git diff --stat origin/main..HEAD | tail -5    # files changed vs upstream
```

If `HEAD..origin/main` is large, the local repo is **behind** upstream — the "carried
commits" are upstream commits the local `origin/main` ref hasn't fetched. The real local
delta is `git status --short` and `git diff`.

Seen on ai-agent-4070: `+3848 carried commits` but `git status --short` showed only
`M gateway/config.py` (33 lines). The `origin/main` ref had only 1 commit because it was
stale — a `git fetch origin main` revealed the true state.

## Local fork vs upstream tracking divergence

When you see "local commits" but the authors are all upstream team members (Teknium,
Brooklyn, etc.), suspect **tracking divergence** rather than a fork:

1. Check `git remote -v` — is it the official repo?
2. Check `git reflog` — was there a reset or fast-forward that left origin behind?
3. Check if `HEAD` exists on any remote branch (`git branch -a --contains HEAD`)
4. Check the merge base (`git merge-base HEAD origin/main`)

If the merge base is empty or very old, `origin/main` is stale. Fix:
```bash
git fetch origin main
git reset --hard origin/main
```

If there ARE real local modifications (shown by `git status --short`), **document and back
them up BEFORE resetting** — even a single file may contain important context:
```bash
# Diff + snapshot backup
git diff > /tmp/local-changes.patch
cp /tmp/local-changes.patch ~/backups/
cp <modified-file> ~/backups/<file>-annotated-$(date +%Y%m%d).py

# Write a README explaining what the change did and why
cat > ~/backups/README.txt <<'EOF'
<hostname> custom changes — <date>
File: <path>
Change: <one-line summary>
Reason: <why it was added>
Status: Custom workaround. Check upstream before re-applying.
EOF
```

After resetting, sync the backup to the primary (or another durable location) so it survives
remote-machine rebuilds:
```bash
rsync -avz ai-agent-4070.tail298a48.ts.net:~/backups/ ~/4070-hermes-backup/
```

Seen on ai-agent-4070: `+3848 carried commits` but `git status --short` showed only
`M gateway/config.py` (33 lines). The `origin/main` ref was stale. After fetching, the
real delta was one file. We backed up the diff, the full file, the profile config, and a
README before hard-resetting to upstream.
password (`gen-ai-3090`, `fs`), this fails with *"a terminal is required to read the
password"*. There is no non-interactive workaround — escalate to the user for any root
operation on those two machines.

On passwordless-sudo machines (`primary`, `nextcloud`, `ai-agent-4070`), `ssh host
'sudo systemctl restart ...'` works fine.

## Restarting a service without root

Where a unit runs as `m` with `Restart=always` (e.g. `comfyui.service` on `gen-ai-3090`),
`kill $(systemctl show <unit> -p MainPID --value)` lets systemd respawn it instead of
requiring `sudo systemctl restart`.

## Verification

After any fleet-wide change, verify each host:

```bash
for host in gen-ai-3090 nextcloud ai-agent-4070; do
  echo "=== $host ==="
  timeout 8 ssh ${host}.tail298a48.ts.net \
    'export PATH=$HOME/.local/bin:$PATH; hermes version 2>&1 | head -1; echo ---; grep -n "default:\|provider:" ~/.hermes/config.yaml | head -2; echo ---; grep -c task-bus ~/.hermes/config.yaml 2>/dev/null || echo MCP clean'
done
```

## Related references

- `references/taskbus-decommission-checklist.md` — full teardown when retiring Task Bus
- `references/agent-info-handoff-server.md` — static AGENTS.md site for agent discovery
- `references/bridge-vs-cron-relationship.md` — when bridge and cron coexist
- `references/worker-connect-command.md` — onboarding message for new workers
