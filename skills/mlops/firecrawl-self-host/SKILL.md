---
name: github-auth
description: "GitHub auth setup: HTTPS tokens, SSH keys, gh CLI login."
version: 1.2.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [GitHub, Authentication, Git, gh-cli, SSH, Setup]
    related_skills: [github-pr-workflow, github-code-review, github-issues, github-repo-management]
---

# GitHub Authentication Setup

This skill sets up authentication so the agent can work with GitHub repositories, PRs, issues, and CI. It covers two paths:

- **`git` (always available)** — uses HTTPS personal access tokens or SSH keys
- **`gh` CLI (if installed)** — richer GitHub API access with a simpler auth flow

## Detection Flow

When a user asks you to work with GitHub, run this check first:

```bash
# Check what's available
git --version
gh --version 2>/dev/null || echo "gh not installed"

# Check if already authenticated
gh auth status 2>/dev/null || echo "gh not authenticated"
git config --global credential.helper 2>/dev/null || echo "no git credential helper"
```

**Decision tree:**
1. If `gh auth status` shows authenticated → you're good, use `gh` for everything
2. If `gh` is installed but not authenticated → use "gh auth" method below
3. If `gh` is not installed → use "git-only" method below (no sudo needed)

---

## Method 1: Git-Only Authentication (No gh, No sudo)

This works on any machine with `git` installed. No root access needed.

### Option A: HTTPS with Personal Access Token (Recommended)

This is the most portable method — works everywhere, no SSH config needed.

**Step 1: Create a personal access token**

Tell the user to go to: **https://github.com/settings/tokens**

- Click "Generate new token (classic)"
- Give it a name like "hermes-agent"
- Select scopes:
  - `repo` (full repository access — read, write, push, PRs)
  - `workflow` (trigger and manage GitHub Actions)
  - `read:org` (if working with organization repos)
- Set expiration (90 days is a good default)
- Copy the token — it won't be shown again

**Step 2: Configure git to store the token**

```bash
# Set up the credential helper to cache credentials
# "store" saves to ~/.git-credentials in plaintext (simple, persistent)
git config --global credential.helper store

# Now do a test operation that triggers auth — git will prompt for credentials
# Username: <their-github-username>
# Password: <paste the personal access token, NOT their GitHub password>
git ls-remote https://github.com/<their-username>/<any-repo>.git
```

After entering credentials once, they're saved and reused for all future operations.

**Alternative: cache helper (credentials expire from memory)**

```bash
# Cache in memory for 8 hours (28800 seconds) instead of saving to disk
git config --global credential.helper 'cache --timeout=28800'
```

**Alternative: set the token directly in the remote URL (per-repo)**

```bash
# Embed token in the remote URL (avoids credential prompts entirely)
git remote set-url origin https://<username>:<token>@github.com/<owner>/<repo>.git
```

**Step 3: Configure git identity**

```bash
# Required for commits — set name and email
git config --global user.name "Their Name"
git config --global user.email "their-email@example.com"
```

**Step 4: Export GITHUB_TOKEN for API calls**

Even though git credentials are stored, `curl`/script-based GitHub API calls need `GITHUB_TOKEN` in the environment. Add it to both `~/.bashrc` and `~/.hermes/.env`:

```bash
# Extract token from the credential store if needed
export GITHUB_TOKEN=$(grep "github.com" ~/.git-credentials 2>/dev/null | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|')
echo "export GITHUB_TOKEN=$GITHUB_TOKEN" >> ~/.bashrc
echo "GITHUB_TOKEN=$GITHUB_TOKEN" >> ~/.hermes/.env
```

See `references/pat-git-only-recipe.md` for the full headless recipe.

**Step 5: Verify**

```bash
# Test push access (this should work without any prompts now)
git ls-remote https://github.com/<their-username>/<any-repo>.git

# Verify identity
git config --global user.name
git config --global user.email

# Verify API access
source ~/.bashrc
curl -s -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user
```

### Option B: SSH Key Authentication

Good for users who prefer SSH or already have keys set up.

**Step 1: Check for existing SSH keys**

```bash
ls -la ~/.ssh/id_*.pub 2>/dev/null || echo "No SSH keys found"
```

**Step 2: Generate a key if needed**

```bash
# Generate an ed25519 key (modern, secure, fast)
ssh-keygen -t ed25519 -C "their-email@example.com" -f ~/.ssh/id_ed25519 -N ""

# Display the public key for them to add to GitHub
cat ~/.ssh/id_ed25519.pub
```

Tell the user to add the public key at: **https://github.com/settings/keys**
- Click "New SSH key"
- Paste the public key content
- Give it a title like "hermes-agent-<machine-name>"

**Step 3: Test the connection**

```bash
ssh -T git@github.com
# Expected: "Hi <username>! You've successfully authenticated..."
```

**Step 4: Configure git to use SSH for GitHub**

```bash
# Rewrite HTTPS GitHub URLs to SSH automatically
git config --global url."git@github.com:".insteadOf "https://github.com/"
```

**Step 5: Configure git identity**

```bash
git config --global user.name "Their Name"
git config --global user.email "their-email@example.com"
```

---

## Method 2: gh CLI Authentication

If `gh` is installed, it handles both API access and git credentials in one step.

### Interactive Browser Login (Desktop)

```bash
gh auth login
# Select: GitHub.com
# Select: HTTPS
# Authenticate via browser
```

### Token-Based Login (Headless / SSH Servers)

```bash
echo "<THEIR_TOKEN>" | gh auth login --with-token

# Set up git credentials through gh
gh auth setup-git
```

### Verification helper

A static re-runnable script is bundled in this skill:

```bash
hermes skill run github-auth:scripts/verify-github-auth.sh
# or manually:
bash ~/.hermes/skills/github/github-auth/scripts/verify-github-auth.sh
```

It checks that `GITHUB_TOKEN` is exported, git identity is set, the API returns the authenticated user, and `git ls-remote` works over HTTPS. Edit the default repo (`Soze-AI-Agent/openclaw`) if needed for your account.

---

## Using the GitHub API Without gh

When `gh` is not available, you can still access the full GitHub API using `curl` with a personal access token. This is how the other GitHub skills implement their fallbacks.

### Setting the Token for API Calls

```bash
# Option 1: Export as env var (preferred — keeps it out of commands)
export GITHUB_TOKEN="<token>"

# Then use in curl calls:
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/user
```

### Extracting the Token from Git Credentials

If git credentials are already configured (via credential.helper store), the token can be extracted:

```bash
# Read from git credential store
grep "github.com" ~/.git-credentials 2>/dev/null | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|'
```

### Helper: Detect Auth Method

Use this pattern at the start of any GitHub workflow:

```bash
# Try gh first, fall back to git + curl
if command -v gh &>/dev/null && gh auth status &>/dev/null; then
  echo "AUTH_METHOD=gh"
elif [ -n "$GITHUB_TOKEN" ]; then
  echo "AUTH_METHOD=curl"
elif _hermes_env="${HERMES_HOME:-$HOME/.hermes}/.env"; [ -f "$_hermes_env" ] && grep -q "^GITHUB_TOKEN=" "$_hermes_env"; then
  export GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" "$_hermes_env" | head -1 | cut -d= -f2 | tr -d '\n\r')
  echo "AUTH_METHOD=curl"
elif grep -q "github.com" ~/.git-credentials 2>/dev/null; then
  export GITHUB_TOKEN=$(grep "github.com" ~/.git-credentials | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|')
  echo "AUTH_METHOD=curl"
else
  echo "AUTH_METHOD=none"
  echo "Need to set up authentication first"
fi
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `git push` asks for password | GitHub disabled password auth. Use a personal access token as the password, or switch to SSH |
| `remote: Permission to X denied` | Token may lack `repo` scope — regenerate with correct scopes |
| `fatal: Authentication failed` | Cached credentials may be stale — run `git credential reject` then re-authenticate |
| `ssh: connect to host github.com port 22: Connection refused` | Try SSH over HTTPS port: add `Host github.com` with `Port 443` and `Hostname ssh.github.com` to `~/.ssh/config` |
| Credentials not persisting | Check `git config --global credential.helper` — must be `store` or `cache` |
| Multiple GitHub accounts | Use SSH with different keys per host alias in `~/.ssh/config`, or per-repo credential URLs |
| `gh: command not found` + no sudo | Use git-only Method 1 above — no installation needed |
| `~/.hermes/.env` is read-protected by Hermes tooling | Use terminal grep/sed/awk or a script file to read values; do not embed token extraction patterns in `execute_code` strings because the literal is redacted and breaks the code |

## References

- `scripts/verify-github-auth.sh` — re-runnable verification of git + API access.
- `references/pat-git-only-recipe.md` — headless PAT-only setup recipe.

---

# Self-hosting Firecrawl

Deploy a production-ish Firecrawl instance on a Linux host with Docker Compose, expose it on a Tailscale magic DNS name, and wire in a local Ollama instance for LLM-powered extraction.

## When to use

- You need a scrape/crawl/extract API for agents on a private network (Tailscale, VPN, local LAN).
- You do not want to use Firecrawl cloud or cloud-only Fire-engine.
- You have Docker, enough RAM (≥8 GB for the API container), and optionally a local Ollama server.

## Images

Use the published GitHub Container Registry images instead of building locally:

- `ghcr.io/firecrawl/firecrawl:latest`
- `ghcr.io/firecrawl/playwright-service:latest`
- `ghcr.io/firecrawl/nuq-postgres:latest`

Replace the upstream `build: apps/...` lines with `image: ghcr.io/...:latest` in `docker-compose.yaml`.

## Known gotcha: nuq-postgres + pg_cron

The `nuq-postgres` image ships `/docker-entrypoint-initdb.d/010-nuq.sql`, which runs:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_cron;
```

`pg_cron` can only be created in the database configured by `cron.database_name`. The default is `postgres`, but the image also sets `POSTGRES_DB` to a custom value (e.g., `firecrawl`). On first boot, PostgreSQL creates `postgres`, then creates the application database, then runs init scripts **in the application database**. `CREATE EXTENSION pg_cron;` therefore fails and the container exits.

**Fix:** provide a custom entrypoint that enables `include_dir = 'conf.d'` and writes a `conf.d/zz-firecrawl-cron.conf` snippet setting `cron.database_name` to the application DB **before** the temporary server used for init scripts starts.

### Custom entrypoint

Save as `nuq-postgres-entrypoint.sh` next to `docker-compose.yaml`, make it executable, and mount it read-only into the `nuq-postgres` container with an `entrypoint:` override.

```bash
#!/usr/bin/env bash
set -Eeo pipefail

PGCONFIGDIR="${PGDATA:-/var/lib/postgresql/data}"

. /usr/local/bin/docker-entrypoint.sh

configure_pg_cron() {
  if [ -n "${POSTGRES_DB:-}" ] && [ "${POSTGRES_DB:-}" != "postgres" ]; then
    mkdir -p "$PGCONFIGDIR/conf.d"
    cat > "$PGCONFIGDIR/conf.d/zz-firecrawl-cron.conf" <<EOF
# Firecrawl self-host: pg_cron must use the application database
cron.database_name = '${POSTGRES_DB}'
EOF
    if ! grep -qxE "^[[:space:]]*include_dir\s*=\s*['\"]?conf.d['\"]?" "$PGCONFIGDIR/postgresql.conf"; then
      sed -i "s/^[#[:space:]]*include_dir\s*=\s*['\"]conf.d['\"].*/include_dir = 'conf.d'/" "$PGCONFIGDIR/postgresql.conf"
      if ! grep -qxE "^[[:space:]]*include_dir\s*=\s*['\"]?conf.d['\"]?" "$PGCONFIGDIR/postgresql.conf"; then
        echo "include_dir = 'conf.d'" >> "$PGCONFIGDIR/postgresql.conf"
      fi
    fi
  fi
}

[ "$1" = 'postgres' ] && shift

docker_setup_env

declare -g DATABASE_ALREADY_EXISTS
: "${DATABASE_ALREADY_EXISTS:=}"
[ -s "$PGDATA/PG_VERSION" ] && DATABASE_ALREADY_EXISTS='true'

if [ -z "$DATABASE_ALREADY_EXISTS" ]; then
  [ "$(id -u)" = '0' ] && exec gosu postgres "$0" postgres "$@"

  docker_init_database_dir
  configure_pg_cron
  pg_setup_hba_conf "$@"
  docker_temp_server_start "$@"

  if [ -n "${POSTGRES_DB:-}" ] && [ "${POSTGRES_DB:-}" != "postgres" ]; then
    POSTGRES_DB= psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --no-password --no-psqlrc \
      --dbname postgres --set db="$POSTGRES_DB" <<-'EOSQL'
      CREATE DATABASE :"db" ;
    EOSQL
    printf '\n'
  fi

  docker_process_init_files /docker-entrypoint-initdb.d/*
  docker_temp_server_stop
else
  cat <<-'EOM'
    PostgreSQL Database directory appears to contain a database; Skipping initialization
  EOM
fi

[ "$(id -u)" = '0' ] && exec gosu postgres postgres "$@"
exec postgres "$@"
```

### Compose override for nuq-postgres

```yaml
  nuq-postgres:
    image: ghcr.io/firecrawl/nuq-postgres:latest
    entrypoint: ["/bin/bash", "/app/nuq-postgres-entrypoint.sh"]
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:-postgres}"
      POSTGRES_DB: ${POSTGRES_DB:-postgres}
    networks:
      - backend
    volumes:
      - nuq-postgres-data:/var/lib/postgresql/data
      - ./nuq-postgres-entrypoint.sh:/app/nuq-postgres-entrypoint.sh:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-postgres}"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 30s
```

Also add `nuq-postgres` as a healthy dependency of the `api` service and declare the `nuq-postgres-data` volume.

## Ollama integration

To enable LLM-powered `/extract` using a local Ollama server on the Docker host:

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434/api
MODEL_NAME=<model-name>       # e.g., gemma4:31b-cloud, llama3.2, qwen3.5
MODEL_EMBEDDING_NAME=<model>  # optional; falls back to default if unset
```

From inside the Firecrawl container, `host.docker.internal` resolves to the host gateway (`172.17.0.1` or similar). Verify with:

```bash
docker exec firecrawl-api-1 curl -s http://host.docker.internal:11434/api/version
```

## Verification

After `docker compose up -d`:

```bash
# API info
curl http://<tailscale-host>:3002/

# Scrape
curl -X POST http://<tailscale-host>:3002/v1/scrape \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'

# LLM extract (self-host path uses /v1/extract)
curl -X POST http://<tailscale-host>:3002/v1/extract \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com"],
    "prompt": "Extract the page title and main heading as JSON with keys title and heading.",
    "schema": {"type":"object","properties":{"title":{"type":"string"},"heading":{"type":"string"}}}
  }'
```

## Systemd auto-start

Create `/etc/systemd/system/firecrawl.service`:

```ini
[Unit]
Description=Firecrawl self-hosted stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/m/firecrawl
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=m
Group=m

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable firecrawl.service
sudo systemctl start firecrawl.service
```

## References

- `references/docker-compose.yaml` — known-good compose for this self-host arrangement
- `references/nuq-postgres-entrypoint.sh` — the pg_cron workaround entrypoint
- `references/firecrawl.env` — example environment file including Ollama wiring
