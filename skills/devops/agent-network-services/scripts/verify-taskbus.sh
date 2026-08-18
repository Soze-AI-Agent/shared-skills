#!/usr/bin/env bash
# verify-taskbus.sh — quick health check for the Hermes Task Bus MCP server.
set -euo pipefail

HOST="${TASKBUS_HOST:-primary.tail298a48.ts.net}"
PORT="${TASKBUS_PORT:-8765}"
URL="http://${HOST}:${PORT}"

echo "==> Checking Task Bus at ${URL}"

# initialize via streamable-http
resp=$(curl -sS -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -X POST "${URL}/mcp" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"verify-script","version":"0.1.0"}}}' \
  | head -c 400)

if echo "$resp" | grep -q '"hermes-task-bus"'; then
  echo "OK: MCP initialize succeeded"
else
  echo "FAIL: unexpected response: $resp"
  exit 1
fi

echo "==> All checks passed."
