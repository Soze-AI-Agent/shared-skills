# Hermes as ACP Agent for Buzz Relay

Connecting a local Hermes agent (Ollama models) to a Buzz relay via the ACP protocol.

## Architecture

```
Buzz Desktop/Mobile ◄──► Buzz Relay ◄──WS──► buzz-acp ◄──stdio──► hermes acp ──► Ollama
```

- `buzz-acp` (Rust) listens for @mentions on the relay
- When mentioned, it spawns `hermes acp --accept-hooks` as a child process
- Hermes processes with local Ollama models and replies via the Buzz CLI

## Prerequisites

- Buzz relay running (Docker Compose or self-hosted)
- Hermes installed (`~/.local/bin/hermes`)
- Ollama running with models (`curl http://localhost:11434/api/tags`)
- Rust toolchain (for building `buzz-acp` and `buzz-cli`)
- Nostr keypair for the agent identity

## Step 1: Generate Agent Keypair

```bash
# On the relay host
docker exec buzz-prod-relay-1 buzz-admin generate-key
# Save pubkey and secret key
```

## Step 2: Register as Relay Member

```bash
docker exec buzz-prod-relay-1 buzz-admin add-member --pubkey <AGENT_PUBKEY>
```

## Step 3: Create Channel and Add Agent

```bash
# Build buzz-cli if needed
cd /path/to/buzz/source
cargo build --release -p buzz-cli

# Create channel
BUZZ_RELAY_URL=http://relay.host:3000 BUZZ_PRIVATE_KEY=<OWNER_SEC> ./target/release/buzz channels create --name general --type public --visibility public

# Add agent as member (use channel UUID from list)
BUZZ_RELAY_URL=http://relay.host:3000 BUZZ_PRIVATE_KEY=<OWNER_SEC> ./target/release/buzz channels add-member --channel <UUID> --pubkey <AGENT_PUB> --role member
```

## Step 4: Build buzz-acp

```bash
cd /path/to/buzz/source
cargo build --release -p buzz-acp
# Binary: target/release/buzz-acp
```

## Step 5: Configure systemd Service

```ini
[Unit]
Description=Buzz ACP Agent Harness (Hermes/Ollama)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/path/to/buzz/source
Environment=PATH=/home/m/.cargo/bin:/home/m/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=BUZZ_PRIVATE_KEY=<AGENT_SECKEY_HEX>
Environment=BUZZ_RELAY_URL=ws://relay.host:3000
Environment=BUZZ_ACP_AGENT_COMMAND=/home/m/.local/bin/hermes-acp-wrapper
Environment=BUZZ_ACP_RESPOND_TO=anyone
Environment=HOME=/home/m
ExecStart=/path/to/buzz/source/target/release/buzz-acp
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

Wrapper script (`~/.local/bin/hermes-acp-wrapper`):
```bash
#!/bin/bash
/home/m/.local/bin/hermes acp --accept-hooks
```

## Step 6: Set Agent Display Name

```bash
BUZZ_RELAY_URL=http://relay.host:3000 BUZZ_PRIVATE_KEY=<AGENT_SECKEY_HEX> ./target/release/buzz users set-profile --name 'hermes-buzz'
```

## Verification

Check logs: `journalctl --user -u buzz-acp -f`

Expected output:
```
buzz-acp: connected to relay at ws://relay.host:3000
buzz-acp: discovered 1 channel(s)
buzz-acp: subscribed to channel <uuid>
buzz-acp: presence set to online
```

## Pitfalls

| Symptom | Cause / Fix |
|---|---|
| `discovered 0 channel(s)` / `no channel subscriptions resolved` | Agent not added as channel member. Use `buzz channels add-member --channel <UUID> --pubkey <PUB> --role member`. |
| `buzz-acp` shows `agent initialized` but no replies | Hermes ACP adapter may need model/provider setup. Run `hermes acp --setup` interactively once. |
| Agent shows raw pubkey as @mention | Set profile name: `buzz users set-profile --name '<name>'` with agent's own keypair. |
| `claude-agent-acp` not found | Install `@agentclientprotocol/claude-agent-acp` via npm if using Claude instead of Hermes. Hermes needs no npm package. |
| Relay container has no `buzz-cli` | The relay Docker image does not include CLI tools. Build `buzz-cli` separately from source or on the host. |
| `docker compose restart relay` doesn't pick up env changes | Must `stop && rm -f && up -d` or `--force-recreate` to re-read `.env`. |
| Agent identity file in raw hex, app expects bech32 nsec | The mobile app stores keys in bech32 format (`nsec1...`). If auto-login fails, check format matches what `_hasValidNsec` expects. |

## Multi-User / Multi-Agent Pattern

- Each agent needs its own Nostr keypair
- Add each pubkey as a relay member
- Add each agent to relevant channels
- Set distinct profile names: `hermes-buzz`, `claude-buzz`, etc.

## Alternative: Direct SQLite (same host only)

If running on the same machine as the relay, bypass HTTP/MCP entirely:
```python
import sqlite3
conn = sqlite3.connect('/mnt/raid/buzz/source/deploy/compose/buzz.db')
# Query channels, messages, membership directly
```

## Related

- `references/buzz-relay-deployment.md` — relay setup
- `references/flutter-mobile-build.md` — mobile client build
- Upstream: https://github.com/block/buzz/tree/main/crates/buzz-acp
