# Tailnet SSH connection troubleshooting

Failure modes actually hit on this tailnet, with the evidence that identified each one.
Work down the ladder — **diagnose before changing anything.** Two of the obvious "fixes"
(clearing `known_hosts`, editing the tailnet ACL) are wrong for every case documented here.

## Don't do these reflexively

| Tempting | Why it's wrong |
|---|---|
| `ssh-keygen -R <host>` on a key-change warning | The warning is usually Tailscale SSH being toggled on/off, which swaps which key answers on :22. Verify against the control plane first — you'll typically find nothing needs clearing. |
| Editing the tailnet ACL when SSH is refused | The stock policy already permits `autogroup:member` → `autogroup:self` for non-root users. It has never been the cause here. |
| Adding to `~/.ssh/authorized_keys` | Irrelevant when Tailscale SSH owns port 22 — it rejects before any key auth, and it doesn't consult `authorized_keys` at all. |
| `-o StrictHostKeyChecking=no` to "just get in" | Discards the one signal that tells you which of the two SSH servers you're talking to. |

---

## `operation not permitted` after successful authentication

**Signature.** `ssh -v` shows authentication *succeeding*, then the session dies:

```
debug1: compat_banner: no match: Tailscale
Authenticated to <host> ([100.x.x.x]:22) using "none".
operation not permitted
```

`using "none"` plus a `Tailscale` banner means **Tailscale SSH**, not sshd, is serving
port 22. The message is EPERM from session setup, not a policy denial.

**Root cause (confirmed on `gen-ai-3090`, 2026-08-14).** `tailscaled` was Canonical's
**snap** build, which is strictly confined. Tailscale SSH cannot work under it —
Snapcraft's own listing says `tailscale ssh` does not work in the snap. AppArmor blocks
exactly what session setup needs. On the target box:

```bash
sudo journalctl -k --since "-1h" | grep -i "apparmor.*DENIED.*tailscale"
```

```
apparmor="DENIED" operation="dbus_method_call" path="/org/freedesktop/login1"
  member="CreateSession" label="snap.tailscale.tailscaled"
apparmor="DENIED" operation="open" name="/etc/ssh/ssh_host_ed25519_key"
  profile="snap.tailscale.tailscaled"
```

Timestamps will line up with your connection attempts. Confirm the build with:

```bash
ps -o args= -p $(pidof tailscaled)     # /snap/... = confined, /usr/sbin/... = apt, fine
snap list tailscale
```

**Fix.** Hand port 22 back to the real sshd:

```bash
sudo tailscale set --ssh=false
```

The MagicDNS name then works immediately, presenting the machine's original sshd host key
— which is usually already trusted, so nothing needs clearing. **Only do this where an
sshd fallback exists** (`primary`, `ai-agent-4070`, `gen-ai-3090`). On `nextcloud` and
`fs` it is a lockout.

The better alternative — **replace the snap with the official apt package** — restores
working Tailscale SSH. This was done on `gen-ai-3090` on 2026-08-14 and is the recommended
fix; `--ssh=false` is the quick unblock, not the cure. Contrary to what you might expect,
migrating does **not** force a host-key change: apt `tailscaled` can read
`/etc/ssh/ssh_host_*` and reuses the machine's existing keys, so both SSH paths end up
presenting the same fingerprint.

Note the snap's auto-refresh is not a safety net — `gen-ai-3090` sat on 1.92.5 from
2026-03-23 to 2026-08-14 with `AutoUpdate: {Check: true, Apply: true}` set, because the
snap cannot self-update. A box can look like it's updating and not be.

### Migrating a host from snap to apt — two traps

1. **The Tailscale node name may not be the OS hostname.** On `gen-ai-3090` the node is
   `gen-ai-3090` but `hostname` returns `ai`. A bare `tailscale up` re-registers it as
   `ai`. Pass `--hostname=<node-name>` explicitly, and delete the stale node in the admin
   console *first* — otherwise the name is still taken and you get `<node-name>-1`.
2. **`tailscale serve` config is keyed on the DNS name and does not follow a rename.**
   After any rename, `sudo tailscale serve reset` then re-apply, or the proxied endpoint
   stops matching and returns nothing at all.

Also: after swapping the package, run `hash -r` before any further bare `tailscale` calls
in the same shell or script. Bash caches the old `/snap/bin/tailscale` path, which no
longer exists, so calls fail with *"No such file or directory"* while `sudo tailscale`
keeps working (sudo does its own PATH lookup). This silently broke a migration script's
verification step.

---

## `REMOTE HOST IDENTIFICATION HAS CHANGED`

**This can be expected when Tailscale SSH is enabled or disabled on a box.** It is not, by
itself, evidence of interception, nor of a reinstall.

Whether the key actually changes depends on the build. When `tailscaled` can read
`/etc/ssh/ssh_host_*` — the normal apt case — Tailscale SSH **reuses the machine's
existing host keys**, so toggling it changes nothing and no warning appears. A confined
**snap** build is denied those reads and generates its own key instead, so toggling it
there does swap the key on :22. That was the source of the warning seen on `gen-ai-3090`
before its migration.

**Verify, don't clear.** Tailscale publishes each Tailscale-SSH node's host keys through
its control plane, which is an independent channel from the connection itself:

```bash
tailscale status --json
```

Find the peer and read its `sshHostKeys`. Fingerprint the ed25519 entry and compare to
what the host presents:

```bash
ssh-keyscan -t ed25519 <host> | ssh-keygen -lf -
```

A match confirms the key is genuine. Known-good fingerprints for all five boxes are
tabulated in `references/tailnet-servers-fleet.md`.

Note `sshHostKeys` is only populated for nodes with Tailscale SSH **enabled**. An empty
list on a box you can still reach means you're talking to its real sshd — compare against
the fingerprint in `references/tailnet-servers-fleet.md` instead.

If you need to inspect without touching the real trust store, connect with an isolated
one rather than disabling checking:

```bash
ssh -o UserKnownHostsFile=/path/to/scratch/kh -o StrictHostKeyChecking=accept-new <host>
```

---

## Diagnostic ladder

1. **Is the node online?** `tailscale status` — offline peers are marked, with a
   last-seen age.
2. **Which server is answering?** `ssh -v <host> 2>&1 | grep -E 'banner|Authenticated'`.
   `using "none"` + `Tailscale` banner = Tailscale SSH; anything else = real sshd.
3. **If Tailscale SSH:** check the build (`snap` vs `/usr/sbin`) and look for AppArmor
   denials on the target. That's the documented failure above.
4. **If real sshd:** ordinary SSH debugging — is `ssh.socket`/`ssh.service` active, does
   `ss -lntH | grep :22` show a listener.
5. **Fallback route.** Some boxes are reachable on the LAN IP where the real sshd listens
   on `0.0.0.0:22` even when Tailscale SSH owns the tailnet IP. `gen-ai-3090` was reached
   at `m@10.0.0.5` throughout its outage. This works only where sshd is installed.
6. **Only then** consider the tailnet policy file — and expect it to be fine.

---

## `systemctl --user` says it can't find the bus

Raw `ssh host 'cmd'` has no login session, so the user bus address is unset:

```bash
ssh <host> 'export XDG_RUNTIME_DIR=/run/user/1000; systemctl --user status <unit>'
```

## A binary "isn't installed" but clearly is

Non-interactive SSH gets a minimal PATH that excludes `~/.local/bin`, `~/.bun/bin`, and
`~/.cargo/bin`. `hermes`, `bun`, and `uv` all live there:

```bash
ssh <host> 'export PATH=$HOME/.local/bin:$HOME/.bun/bin:$HOME/.cargo/bin:$PATH; <cmd>'
```

## A service needs restarting but `sudo systemctl` prompts

Where the unit runs as `m` with `Restart=always`, kill it and let systemd respawn:

```bash
ssh <host> 'kill $(systemctl show <unit> -p MainPID --value)'
```

On **`fs` and `gen-ai-3090`** sudo needs a password, and `ssh host 'sudo ...'` has no TTY
for the prompt — it fails with *"a terminal is required to read the password"*. There is no
non-interactive way around it: escalate to the user and have them run it at a terminal.

Don't infer sudo rights from a successful privileged-looking read. On `gen-ai-3090`, `m` is
in the `adm` group, so `journalctl -k` works fine without sudo — that is group permission,
not passwordless sudo.

## Re-enabling Tailscale SSH re-breaks a snap box

`tailscale set --ssh=true` on a host still running the **snap** build restores the original
`operation not permitted` failure immediately, and swaps the key answering on :22 back to
the Tailscale SSH one. Only enable it after migrating that host to the apt package and
confirming `command -v tailscaled` reports `/usr/sbin/tailscaled`. Recovery is
`sudo tailscale set --ssh=false` at a terminal (needs a password on `gen-ai-3090`).
