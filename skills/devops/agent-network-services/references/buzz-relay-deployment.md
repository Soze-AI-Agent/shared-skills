# Buzz Relay Deployment — Production Compose on Tailscale

Deploy the Block Buzz relay as a Docker Compose stack on the primary host,
exposed over Tailscale to the agent network.

## Quick start

```bash
git clone https://github.com/block/buzz.git
cd buzz/deploy/compose
cp .env.example .env
# Edit .env (see below)
./run.sh start
```

For a public VPS with TLS:
```bash
BUZZ_COMPOSE_TLS=true ./run.sh start
```

## Environment (.env) for Tailscale deployment

```bash
BUZZ_IMAGE=ghcr.io/block/buzz:main
BUZZ_DOMAIN=primary.tail298a48.ts.net
RELAY_URL=ws://primary.tail298a48.ts.net:3000
BUZZ_MEDIA_BASE_URL=http://primary.tail298a48.ts.net:3000/media
BUZZ_MEDIA_SERVER_DOMAIN=primary.tail298a48.ts.net
BUZZ_CORS_ORIGINS=http://primary.tail298a48.ts.net

# Open relay — Tailscale is the security boundary
BUZZ_REQUIRE_AUTH_TOKEN=false
BUZZ_REQUIRE_RELAY_MEMBERSHIP=false
BUZZ_ALLOW_NIP_OA_AUTH=true
BUZZ_AUTO_MIGRATE=true
BUZZ_GIT_CONFORMANCE_PROBE=true
RUST_LOG=buzz_relay=info,buzz_db=info,buzz_auth=info,buzz_pubsub=info,tower_http=info

# Owner identity — generate with: docker exec <relay> buzz-admin generate-key
RELAY_OWNER_PUBKEY=<64-char-hex>
BUZZ_RELAY_PRIVATE_KEY=<64-char-hex>

# Stable secrets — generate once, back up securely
BUZZ_GIT_HOOK_HMAC_SECRET=<64-char-hex>
POSTGRES_DB=buzz
POSTGRES_USER=buzz
POSTGRES_PASSWORD=<random>
REDIS_PASSWORD=<random>
BUZZ_S3_ACCESS_KEY=<random>
BUZZ_S3_SECRET_KEY=<random>
BUZZ_S3_BUCKET=buzz-media
BUZZ_S3_ADDRESSING_STYLE=path

# Ports
BUZZ_HTTP_PORT=3000
CADDY_HTTP_PORT=80
CADDY_HTTPS_PORT=443
POSTGRES_PORT=5432
REDIS_PORT=6379
MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001
```

## Expose health port (8080)

The relay's readiness probe runs on port 8080 inside the container.
Expose it by adding to `compose.yml` under the relay service:

```yaml
ports:
  - "${BUZZ_HTTP_PORT:-3000}:3000"
  - "8080:8080"
```

## Generate owner keypair

```bash
docker exec <relay-container> buzz-admin generate-key
```

Update `.env` with the generated pubkey and private key, then recreate the relay:

```bash
docker compose stop relay && docker compose rm -f relay
docker compose up -d relay
```

## Auto-start on boot (systemd)

```ini
[Unit]
Description=Buzz relay Docker Compose stack
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/m/buzz/deploy/compose
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
ExecReload=/usr/bin/docker compose restart
User=m
Group=m

[Install]
WantedBy=multi-user.target
```

Enable: `sudo systemctl enable --now buzz-relay`

## Verification

| Check | Command |
|---|---|
| Liveness | `curl -fsS http://primary.tail298a48.ts.net:3000/_liveness` |
| Readiness | `curl -fsS http://primary.tail298a48.ts.net:8080/_readiness` |
| NIP-11 info | `curl -s http://primary.tail298a48.ts.net:3000/` |
| WebSocket | Python `socket.connect` + upgrade headers → `101 Switching Protocols` |

## Agent identity

Generate a keypair per agent and store in `~/.buzz/agent-<name>.env`:

```bash
docker exec <relay> buzz-admin generate-key
```

## Pitfalls

| Symptom | Cause / Fix |
|---|---|
| `curl: (7) Failed to connect to localhost port 8080` | Port 8080 not exposed in compose.yml. Add `- "8080:8080"` and recreate relay. |
| `no community is configured for this host` | Request used IP address or wrong Host header. Use MagicDNS hostname (`primary.tail298a48.ts.net:3000`) in the Host header. |
| Relay owner still `0000...` after .env edit | `docker compose restart relay` does not pick up new env vars. Use `stop && rm -f && up -d` or `docker compose up -d --force-recreate relay`. |
| `metrics exporter must build exactly once: Address already in use` | Port 9102 conflict. Check `BUZZ_METRICS_PORT` env and ensure no other process uses it. |
| `buzz-cli` not found in relay container | The relay image does not include `buzz-cli`. Install it separately on agent hosts or build from source. |
