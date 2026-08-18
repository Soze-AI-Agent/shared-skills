# Tailnet servers — Fleet reference

Per-host detail for the five documented boxes on `tail298a48.ts.net`.
All facts below were verified live on **2026-08-14**. Anything marked *(from prior
session notes)* was carried over rather than re-verified in that sweep.

Common to all five: login user **`m`** (uid 1000), home `/home/m`, x86_64, Ubuntu,
no password needed to connect.

---

## `gen-ai-3090` — GPU generation box

| | |
|---|---|
| Tailnet IP | **100.127.56.74** (changed 2026-08-14) · LAN **10.0.0.5** |
| `hostname` | `ai` (note: not "gen-ai-3090" — the Tailscale node name differs from the OS hostname) |
| OS / kernel | Ubuntu 24.04.4 LTS · 6.8.0-137-generic |
| GPU | NVIDIA RTX 3090, 24576 MiB |
| `sudo -n` | **needs a password** (`m` is in `adm`, so journal reads work without it — don't mistake that for passwordless sudo) |
| Access | Tailscale SSH · real sshd fallback on the LAN IP |
| Host key (ed25519) | `SHA256:BDvZeFvPiPtWZsrr1OR2ijrusc+UD5iVF4+zpHA2McI` — same key on both paths |
| Storage | `/` 234G (46G avail) · `/mnt/ai` 938G · `/mnt/data` 7.3T (1.7T avail) · `/mnt/raid` 3.6T (2.4T avail) |

**Migrated off the Canonical snap to the official apt package on 2026-08-14** (now
1.102.2, `/usr/sbin/tailscaled`). Under snap confinement Tailscale SSH could not work at
all; on apt it works, and was enabled. Because apt `tailscaled` can read
`/etc/ssh/ssh_host_*`, Tailscale SSH reuses the machine's existing host key rather than
generating its own — so both access paths present the same fingerprint and no re-trusting
was needed.

Two traps from that migration, worth knowing before touching this box again:
- The Tailscale node name (`gen-ai-3090`) is **not** the OS hostname (`ai`). Re-registering
  without `--hostname=gen-ai-3090` names it `ai`; re-registering while a stale node still
  holds the name produces `gen-ai-3090-1`. Both silently break `SPACES_ENDPOINT_V2`.
- **`tailscale serve` config is keyed on the DNS name**, and does not follow a rename.
  After any node rename, `sudo tailscale serve reset` and re-apply, or the `:9443` MinIO
  endpoint stops matching and returns nothing.

**Services**

- **ComfyDeploy** (self-hosted, billing-stripped fork) — systemd *user* service
  `comfydeploy`, install dir `/mnt/ai/comfydeploy`. API (FastAPI/uvicorn) on **:3011**,
  web (Vite) on **:3001**. `systemctl --user restart comfydeploy` to bounce.
  Logs: `/tmp/comfydeploy-api.log` and `journalctl --user -u comfydeploy`.
- **ComfyUI** — system unit `comfyui.service` (`User=m`, `Restart=always`), listens on
  `10.0.0.5:8188`, output dir `/mnt/raid/output`. Restart without root by killing MainPID.
- **MinIO** — object storage for ComfyDeploy, `:9000` (API) / `:9001` (console), plus a
  `tailscale serve` proxy on **:9443**. Bucket `comfydeploy-dev-storage`.
- Support stack in Docker: Postgres `:5480`, Redis `:6379`, serverless-redis-http `:8079`.
- **NodeTool** on `:17777`; Ollama bound to `127.0.0.1:11434`.

**Hermes** v0.18.2 · `default` profile only · `hermes-gateway` user service active.
The HTTP API server is **not** enabled (nothing on :8642).

---

## `ai-agent-4070` — agent + Archeion box

| | |
|---|---|
| Tailnet IP | 100.117.11.2 |
| `hostname` | `ai-agent` |
| OS / kernel | Ubuntu 24.04.4 LTS · 6.17.0-35-generic |
| GPU | NVIDIA RTX 4070 Ti, 12282 MiB |
| `sudo -n` | passwordless |
| Access | Tailscale SSH · sshd fallback present (socket-activated) |
| Host key (ed25519) | `SHA256:aQkmITqTYtglqWfj0ajoYpShsEYDrbJj4un3vRkygqU` |
| Storage | `/` 233G (49G avail) · `/mnt/altsys` 234G · `/mnt/data` 1.9T (1018G avail) |

**Services**

- **Archeion** — `archeion-api.service`, `archeion-worker.service`; Docker
  `archeion-postgres` (Postgres 16 on **:5433**) and `archeion-qdrant`
  (Qdrant v1.11.3 on **:6333-6334**).
- **ComfyUI** — `comfyui.service`.
- MariaDB, Samba (139/445), web on :80/:443, port :3003, RDP on :3389/:3390.

**Hermes** v0.19.0 — a **local fork** (`+3848 carried commits`), so treat upstream docs
with extra suspicion here. Profiles: `default` and **`polymarket`**.

`~/Claude-Projects/Hermes-Polymarket` is the git source of truth for the paper-trading
system. Its app entry point is Caddy on **:8080**; debug ports are bound to 127.0.0.1 only.
Invoke the trading agent as `hermes -p polymarket chat -Q -q "<task>"` — and only when the
task is genuinely about that system.

---

## `primary` — scraping + local inference

| | |
|---|---|
| Tailnet IP | 100.99.71.23 |
| `hostname` | `Primary-AI` |
| OS / kernel | Ubuntu 24.04.4 LTS · 7.0.0-28-generic |
| GPU | none |
| `sudo -n` | passwordless |
| Access | Tailscale SSH · sshd fallback present |
| Host key (ed25519) | `SHA256:0hpv7WHowcUcdYS091uyjxtXkjrzOIvAhaJVppnnU7s` |
| Storage | `/` 457G (384G avail) · `/mnt/data` 458G (435G avail) |

**Services**

- **Firecrawl** stack in Docker (5 containers): `rabbitmq:3-management`, `redis:alpine`,
  `foundationdb:7.3.63`, `playwright-service`, `nuq-postgres`.
- **Ollama** — `ollama.service`, `:11434`.
- Port `:8765` on the tailnet IP; nginx/apache on `:80`; `gnome-remote-desktop`.
- It also runs a `snap.nextcloud.apache.service`. **This is a stale duplicate** — the real
  Nextcloud is the `nextcloud` box. Confirmed by the user 2026-08-14.

**Hermes** v0.18.2 · `default` profile only · gateway active.
Knowledge base at `~/Soze-AI-Agents-KnowledgeBase`.

Tailscale here is apt 1.98.8 — older than the 1.102.1 on the other three.

---

## `nextcloud` — personal cloud + RAID

| | |
|---|---|
| Tailnet IP | 100.88.115.124 |
| `hostname` | `nextcloud` |
| OS / kernel | **Ubuntu 26.04 LTS** · 7.0.0-29-generic |
| GPU | none |
| `sudo -n` | passwordless |
| Access | **Tailscale SSH ONLY — no `openssh-server` installed** |
| Host key (ed25519) | `SHA256:hcFwYCRNLU/QBW1Vn+jkVgHfs/Om9Ddw5UePp+tXc/E` |
| Storage | `/` 457G (403G avail) · **`/mnt/raid` 1.8T (1.7T avail)** |

> [!CAUTION]
> No sshd. Disabling Tailscale SSH here locks you out with no remote recovery.

**Services**

- Docker: `nextcloud-app` (`nextcloud:stable`, published to `127.0.0.1:8080->80`) and
  `nextcloud-db` (`mariadb:10.11`).
- Host `apache2` and `mariadb` services; HTTPS on `:443`; Samba on 139/445.
- `mdmonitor` — this box has the software RAID array.

**Hermes** v0.20.0 — the **newest** version in the fleet · `default` only · gateway active.
Useful as the reference box when checking whether a Hermes behaviour is version-specific.

The only Ubuntu 26.04 machine in the fleet; don't assume package versions match the others.

---

## `fs` — DNS + media file server

| | |
|---|---|
| Tailnet IP | 100.88.234.126 |
| `hostname` | `fs` |
| OS / kernel | Ubuntu 24.04.4 LTS · 6.8.0-124-generic |
| GPU | none |
| `sudo -n` | **needs a password** — the only such box |
| Access | **Tailscale SSH ONLY — no `openssh-server` installed** |
| Host key (ed25519) | `SHA256:K+t0WXCZ+QYNe9nIkg1P3HkKAvz0zkqz/R+0QzUF7JM` |
| Storage | `/` 55G (32G avail) · **`/mnt/media` 3.7T (1.7T used, 2.0T avail)** |

> [!CAUTION]
> This box serves **Pi-hole DNS for the network**. If it goes down, name resolution
> breaks for everything. It also has no sshd and no passwordless sudo — the least
> recoverable machine in the fleet. Treat it as read-only unless the user says otherwise.

**Services**

- **Pi-hole** — `pihole-FTL.service`, DNS on `:53`, admin web on `:80`/`:443`.
- **Samba** — `nmbd` + smbd on 139/445, serving `/mnt/media`.
- `meshagent`, `gnome-remote-desktop`.
- No Docker. No Hermes.

Knowledge base at `~/Soze-KB` (distinct from `~/Soze-AI-Agents-KnowledgeBase` elsewhere).

---

## Quick comparison

| | gen-ai-3090 | ai-agent-4070 | primary | nextcloud | fs |
|---|---|---|---|---|---|
| GPU | 3090 24G | 4070 Ti 12G | — | — | — |
| Passwordless sudo | **no** | yes | yes | yes | **no** |
| sshd fallback | yes (LAN IP) | yes | yes | **none** | **none** |
| Tailscale SSH | on | on | on | on | on |
| Tailscale build | apt 1.102.2 | apt 1.102.1 | apt 1.98.8 | apt 1.102.1 | apt 1.102.1 |
| Hermes | 0.18.2 | 0.19.0 (fork) | 0.18.2 | 0.20.0 | none |
| Docker | yes | yes | yes | yes | no |
| Biggest volume | 7.3T `/mnt/data` | 1.9T `/mnt/data` | 458G `/mnt/data` | 1.8T `/mnt/raid` | 3.7T `/mnt/media` |
