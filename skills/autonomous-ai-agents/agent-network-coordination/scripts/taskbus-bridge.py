#!/usr/bin/env python3
"""
Task Bus Bridge — full worker loop, zero LLM tokens.

Handles heartbeat, read_messages, and claim_task directly via MCP streamable-http.
Only wakes the Hermes API server when there's actual work.

Usage:
  TASKBUS_URL=http://primary.tail298a48.ts.net:8765/mcp \
  HERMES_API_URL=http://localhost:8766/v1/chat/completions \
  HERMES_API_KEY=*** \
  AGENT_ID=primary \
  POLL_INTERVAL=3 \
  python3 taskbus-bridge.py
"""

import json
import os
import sys
import time
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timezone


# ── config ──────────────────────────────────────────────────────────
TASKBUS_URL = os.environ.get("TASKBUS_URL", "http://primary.tail298a48.ts.net:8765/mcp")
HERMES_API_URL = os.environ.get("HERMES_API_URL", "http://localhost:8766/v1/chat/completions")
HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "")
AGENT_ID = os.environ.get("AGENT_ID", "primary")
CAPABILITIES_RAW = os.environ.get("CAPABILITIES", "[]")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "3"))
COOLDOWN_SECONDS = int(os.environ.get("COOLDOWN_SECONDS", "10"))

# Parse capabilities — handle both JSON array and comma-separated fallback
# (systemd strips inner double-quotes from Environment= JSON values)
try:
    CAPABILITIES = json.loads(CAPABILITIES_RAW)
except (json.JSONDecodeError, TypeError):
    CAPABILITIES = [
        c.strip().strip("\"'")
        for c in CAPABILITIES_RAW.strip("[]").split(",")
        if c.strip()
    ]

# ── state ───────────────────────────────────────────────────────────
last_wake = 0.0
last_state_hash = ""
_prev = {}
_session_id = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mcp_request(method: str, params: dict) -> dict:
    """Send a JSON-RPC request to the MCP server, managing sessions."""
    global _session_id

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if _session_id:
        headers["Mcp-Session-Id"] = _session_id

    req = urllib.request.Request(
        TASKBUS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                _session_id = sid
            raw = resp.read().decode("utf-8")
        if not raw or not raw.strip():
            return {}
        # Parse SSE response: "event: message\ndata: {...}\n\n"
        if raw.startswith("event:") or "data:" in raw:
            text = ""
            for line in raw.splitlines():
                if line.startswith("data: "):
                    text = line[6:]
                    break
            if text:
                return json.loads(text)
            return {}
        return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[{_now()}] MCP {method} HTTP {e.code}: {body[:200]}", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"[{_now()}] MCP {method} failed: {e}", file=sys.stderr)
        return {}


def _mcp_initialize() -> bool:
    """Establish MCP session via initialize handshake."""
    global _session_id
    _session_id = None

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "taskbus-bridge", "version": "1.0.0"},
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    req = urllib.request.Request(
        TASKBUS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if not sid:
                print(f"[{_now()}] MCP init: no session ID in response", file=sys.stderr)
                return False
            _session_id = sid
            raw = resp.read().decode("utf-8")
            print(f"[{_now()}] MCP session established: {sid[:16]}...", file=sys.stderr)
        # Send initialized notification (expected to return 400 — harmless)
        try:
            notif = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }
            nreq = urllib.request.Request(
                TASKBUS_URL,
                data=json.dumps(notif).encode("utf-8"),
                headers={"Content-Type": "application/json", "Mcp-Session-Id": _session_id},
            )
            urllib.request.urlopen(nreq, timeout=5)
        except Exception:
            pass  # 400 expected for streamable-http notifications
        return True
    except Exception as e:
        print(f"[{_now()}] MCP init exception: {e}", file=sys.stderr)
        return False


def _wake_hermes(reason: str):
    """Send a wake-up message to the Hermes API server."""
    global last_wake
    now = time.time()
    if now - last_wake < COOLDOWN_SECONDS:
        return
    last_wake = now

    payload = {
        "model": "hermes-coordinator",
        "messages": [
            {
                "role": "user",
                "content": (
                    f"[AUTO-WAKE from taskbus-bridge] {reason}\n\n"
                    "Check the Task Bus for new events and process them. "
                    "Do not reply to this wake-up message."
                ),
            }
        ],
    }
    req = urllib.request.Request(
        HERMES_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {HERMES_API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            pass
        print(f"[{_now()}] Woke Hermes: {reason}")
    except Exception as e:
        print(f"[{_now()}] Wake failed: {e}", file=sys.stderr)


def _hash_state(state: dict) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def poll():
    """Full worker loop: heartbeat, read_messages, claim_task. Wake on work."""
    global last_state_hash, _prev

    # 1. Heartbeat
    _mcp_request("heartbeat", {"worker_id": AGENT_ID})

    # 2. Read messages
    messages = _mcp_request("read_messages", {
        "agent_id": AGENT_ID, "unread_only": True, "mark_read": False, "limit": 20
    })
    msg_ids = [m.get("id") for m in messages.get("result", []) if isinstance(m, dict)]

    # 3. Claim task
    task = _mcp_request("claim_task", {"worker_id": AGENT_ID, "task_types": CAPABILITIES})
    task_id = task.get("result", {}).get("id") if isinstance(task, dict) else None

    # 4. Build state hash for change detection
    state = {
        "message_ids": msg_ids,
        "claimed_task": task_id,
    }
    new_hash = _hash_state(state)

    # 5. Wake if something changed
    if last_state_hash and new_hash != last_state_hash:
        reasons = []
        if msg_ids:
            reasons.append(f"{len(msg_ids)} new message(s)")
        if task_id:
            reasons.append(f"task {task_id[:8]} claimed")
        if reasons:
            _wake_hermes(", ".join(reasons))

    last_state_hash = new_hash
    _prev = state


def main():
    print(f"[{_now()}] taskbus-bridge starting: agent={AGENT_ID}, poll={POLL_INTERVAL}s", file=sys.stderr)
    print(f"[{_now()}] CAPABILITIES: {CAPABILITIES!r}", file=sys.stderr)
    if not HERMES_API_KEY:
        print(f"[{_now()}] WARNING: HERMES_API_KEY not set — wake-ups will fail", file=sys.stderr)

    # Establish MCP session
    try:
        if not _mcp_initialize():
            print(f"[{_now()}] FATAL: could not establish MCP session", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"[{_now()}] FATAL: MCP init exception: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    # Seed initial state
    global last_state_hash
    poll()
    last_state_hash = _hash_state(_prev)

    while True:
        try:
            time.sleep(POLL_INTERVAL)
            poll()
        except KeyboardInterrupt:
            print(f"[{_now()}] shutting down", file=sys.stderr)
            break
        except Exception as e:
            print(f"[{_now()}] poll error: {e}", file=sys.stderr)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
