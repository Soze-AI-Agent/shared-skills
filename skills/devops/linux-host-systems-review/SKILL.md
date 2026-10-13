---
name: linux-host-systems-review
description: "Use when auditing a Linux host: units, exposure, perf."
version: 1.0.0
license: MIT
author: Hermes Agent
platforms: [linux]
metadata:
  hermes:
    tags: [devops, linux, systemd, security, audit, troubleshooting]
---

# Linux host systems review

## When to Use

Trigger: "run a systems check", "health check", "what's wrong with this box", "look for
issues and perf improvements" on a Linux host this user owns — a fleet box, a server, or
the local machine. The goal is a report of what was fixed, what is still broken, and what
is optional, backed by real command output with numbers before and after. This is
host-level triage; for app-level bugs, debug the app instead.

## Order of work

1. **Recon, read-only, in parallel batches.** `scripts/host-review.sh` in this skill
   collects the whole picture in one shot: uptime/load, mem+swap, per-fs disk and
   inodes, top CPU/mem processes, failed units (system AND `--user`), every listening
   socket with its bind address, zombies, kernel errors this boot, journal size,
   `docker system df`, apt pending, reboot-required, and sshd/scheduler/swappiness.
   Read it, don't re-derive it.
2. **Crash loops first.** A restart counter is the highest-value finding: invisible in
   a normal `systemctl status` glance, and it can burn tens of percent of CPU forever.
3. **Exposure next** — anything on `0.0.0.0` / `*:` with no auth.
4. **Reclaim** — journal, docker build cache + dangling images/volumes, oversized app
   data, duplicate copies of big directories.
5. **Report**, then fix only with consent where the action is destructive.

## Rules that matter

- A unit can report `active (running)` and still be useless. Read
  `systemctl [--user] show <unit> -p ActiveState -p SubState -p NRestarts` and grep the
  journal for `Scheduled restart job`. A climbing `NRestarts` means every start died;
  the service is down however green the status line looks.
- `active (exited)` is a SUCCESS for `Type=oneshot` units such as a
  `docker compose up -d` boot unit. Do not "fix" it.
- Clear the cause, not the symptom. A loop means something refuses every start — stale
  lock/PID record, port already bound, missing permission. `reset-failed` alone never
  fixes a persistent refusal.
- Verify with the real endpoint, not the unit state: `curl` the port, call the tool.
  Then wait 40-60s and re-read `NRestarts` — a fix that looks clean for 5s and loops
  again has not been fixed.
- Stale state is usually spread across more than one file or scope. When you find one
  stale lock, search for siblings (pid/sock/state json, host-scoped copies under
  `~/.local/state/<app>/`) before concluding the cleanup is done.

## Privileged work

- Batch every root step into ONE script written to the scratch dir, then run it with a
  single `sudo bash <path>`. Do not chain many `sudo` commands, and do not pipe a heredoc
  into `sudo bash -s` — a long privileged invocation can sit waiting for approval and
  time out, and a timeout means **nothing ran**. Never retry a blocked command; re-issue
  the work as a written script instead.
- Check for passwordless sudo early (`sudo -n true`) so you know whether the plan is
  executable in one approval or needs the user.
- Back up every file you replace into one dated directory (`/root/<task>-backup-<ts>`) and
  name that path in the report.
- Prefer the package's own drop-in directories (`/etc/systemd/journald.conf.d/`,
  `/etc/systemd/system/<unit>.d/`, `/etc/ssh/sshd_config.d/`, `/etc/modprobe.d/`,
  `/etc/udev/rules.d/`) over editing shipped files. Validate before reloading where a
  validator exists (`sshd -t`, `nginx -t`).

## Pitfalls

- **User-scope units cannot hold capabilities for you.**
  `AmbientCapabilities=CAP_NET_BIND_SERVICE` in a `systemctl --user` unit fails with
  `Failed to drop capabilities: Operation not permitted` (exit `218/CAPABILITIES`),
  because the user manager has no privilege to grant. To serve a port below 1024,
  install a SYSTEM unit with `User=<user>` + `AmbientCapabilities=CAP_NET_BIND_SERVICE`
  and retire the user unit — a same-named unit in both scopes is a duplicate-owner trap.
- **A `/lib/udev/rules.d/<n>-<name>.rules` file is replaced wholesale by a same-named
  file in `/etc/udev/rules.d/`.** Write a comment-only file there to neutralize a rule
  without touching the package's copy; `udevadm control --reload-rules` applies it.
- **A loop that floods the kernel log is a rule or hook re-running a command that can
  never succeed.** Measure the rate (`journalctl -k --since "30 sec ago" | grep -c ...`)
  and walk up from the repeating process with `ps -o ppid=`. Disabling the daemon is not
  enough if udev or a kernel-side trigger re-fires it: also stop the module from ever
  loading (`install <mod> /bin/true` + `blacklist` in `/etc/modprobe.d/`).
- **journald is uncapped on many installs** (`SystemMaxUse` left commented out) and is a
  routine multi-GB surprise. Report `journalctl --disk-usage`, cap it in a drop-in, then
  `journalctl --vacuum-size=`.
- **Docker bypasses ufw.** Published container ports stay reachable under default-deny;
  never tell the user a firewall closed a container port.
- **`ss -tlnp` cannot name the owner of another user's socket.** Use `ss -tlnpH` and match
  by port, or read the unit's `ListenStream`.
- **Exposure triage needs a probe, not a guess.** List every `0.0.0.0` / `*:` listener and
  test it (`curl -m 3`) before calling it internal. Bind unauthenticated local services
  to 127.0.0.1 or the VPN/tailnet address, never `0.0.0.0`.
- **Before disabling SSH password auth, confirm `~/.ssh/authorized_keys` is non-empty and
  looks valid** (`awk '{print $1,$3}'`) — otherwise the change locks the user out.

## Before decommissioning any service

Grep the app configs for the service's name, port, and URL before stopping it. A "barely
used" self-hosted service is often the configured backend of a tool every agent and cron
job depends on. Surface the tradeoff and let the user choose the replacement; if a keyless
substitute exists, prove it works end-to-end first, then remove and archive the compose
file plus `.env` somewhere they can restore from.

## Reporting shape

Fixed / still broken / optional are three separate lists. Give exact numbers ("journal
4.0G -> 136M", "disk 81G -> 65G used"), state where the backups live, quote the shortest
decisive error line rather than dumping logs, and close with the smallest set of actions
still needing the user's approval — each one already scripted.

## Support files

- `scripts/host-review.sh` — read-only recon pass, safe to run on any Linux host; no
  sudo, no mutations. Run this first.
