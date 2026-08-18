#!/usr/bin/env python3
"""
Worker tick script for Hermes cron workers on the Soze AI agent network.

Two modes:
  1. Bridge mode (default): verify bridge is healthy, exit silently if so.
  2. Direct mode (fallback): call MCP tools directly via HTTP when bridge is down.

Usage in cron prompt:
  python3 /home/m/.hermes/scripts/worker-tick.py 2>&1

Requires: pip install mcp httpx (for bridge mode)
Tested with: mcp>=1.26.0 (3-tuple unpack from streamable_http_client)

Customize: WORKER_ID, URL, TASK_TYPES, and task execution handlers below.
"""
import asyncio, json, subprocess, sys, os, urllib.request

# === CONFIGURE THESE ===
WORKER_ID = "3090-agent"
URL = "http://primary.tail298a48.ts.net:8765/mcp"
TASK_TYPES = ["docker-maintenance", "linux-admin", "web-hosting", "nextcloud-support"]
BRIDGE_SERVICE = "taskbus-bridge"


def check_bridge():
    """Check bridge health. Returns (healthy: bool, reason: str)."""
    r = subprocess.run(
        ["systemctl", "--user", "is-active", BRIDGE_SERVICE],
        capture_output=True, text=True, timeout=10
    )
    if r.returncode != 0:
        return False, f"BRIDGE_DOWN: {r.stdout.strip()}"

    r2 = subprocess.run(
        ["journalctl", "--user", "-u", BRIDGE_SERVICE, "--since", "5 minutes ago",
         "--no-pager", "--output=cat"],
        capture_output=True, text=True, timeout=10
    )
    fail_count = r2.stdout.count("failed") + r2.stdout.count("timeout") + r2.stdout.count("error")
    if fail_count > 5:
        return False, f"BRIDGE_BROKEN: {fail_count} failures in 5 min"

    return True, ""


def check_stale_workers(db_path="/opt/taskbus/taskbus.db"):
    """Check for stale workers via direct SQLite access (same-host only)."""
    import sqlite3
    from datetime import datetime, timezone
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT id, status, last_heartbeat FROM workers ORDER BY last_heartbeat")
        stale = []
        for r in cur.fetchall():
            w = dict(r)
            if w["status"] == "online":
                hb = datetime.fromisoformat(w["last_heartbeat"])
                age = (datetime.now(timezone.utc) - hb).total_seconds()
                if age > 300:
                    stale.append({"id": w["id"], "last_heartbeat": w["last_heartbeat"], "stale_seconds": int(age)})
        conn.close()
        return stale
    except Exception as e:
        return {"error": str(e)}


def send_message_to_primary(session_id, stale_workers):
    """Send stale worker alert to primary via MCP."""
    result, _ = _mcp_http_call("tools/call", {
        "name": "send_message",
        "arguments": {
            "sender": WORKER_ID,
            "recipient": "primary",
            "subject": "stale workers detected",
            "body": json.dumps({"stale_workers": stale_workers, "note": f"Reported by {WORKER_ID} cron cycle"})
        }
    }, session_id)
    return result


# ── Direct MCP HTTP fallback (no bridge) ──────────────────────────────

def _mcp_http_call(method, params, session_id=None):
    """Call MCP tool via direct HTTP. Used when bridge is down."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    data = json.dumps(payload).encode()
    req = urllib.request.Request(URL, data=data, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        sid = resp.headers.get("Mcp-Session-Id")
        raw = resp.read().decode()
        for line in raw.split("\n"):
            if line.startswith("data:"):
                return json.loads(line[5:].strip()), sid
        return {}, sid
    except Exception as e:
        return {"error": str(e)}, None


def _extract_text(result):
    """Extract text content from MCP tool result."""
    content = result.get("result", {}).get("content", [])
    if content and isinstance(content, list):
        return content[0].get("text", "")
    return ""


def direct_tick():
    """Full worker tick via direct MCP HTTP calls (no bridge)."""
    print(f"=== Worker {WORKER_ID} direct tick ===")

    init_result, sid = _mcp_http_call("initialize", {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": f"{WORKER_ID}-cron", "version": "1.0"}
    })
    if not sid:
        print("FATAL: no MCP session")
        return
    _mcp_http_call("notifications/initialized", {}, sid)
    print("MCP session initialized")

    result, _ = _mcp_http_call("tools/call", {"name": "heartbeat", "arguments": {"worker_id": WORKER_ID}}, sid)
    hb_text = _extract_text(result)
    print(f"Heartbeat: {hb_text[:100] if hb_text else 'OK'}")

    result, _ = _mcp_http_call("tools/call", {"name": "read_messages", "arguments": {
        "agent_id": WORKER_ID, "unread_only": True, "mark_read": True, "limit": 20
    }}, sid)
    msg_text = _extract_text(result)
    msgs = json.loads(msg_text) if msg_text else []
    if msgs:
        print(f"Messages ({len(msgs)}):")
        for m in msgs:
            print(f"  [{m.get('from','?')}] {m.get('subject','')[:100]}")
    else:
        print("Messages: none unread")

    result, _ = _mcp_http_call("tools/call", {"name": "claim_task", "arguments": {
        "worker_id": WORKER_ID, "task_types": TASK_TYPES
    }}, sid)
    task_text = _extract_text(result)
    task = json.loads(task_text) if task_text else None
    if task and task.get("id"):
        tid = task["id"]
        ttype = task.get("task_type", "?")
        payload = task.get("payload", {})
        print(f"\nTask claimed: {tid} ({ttype})")
        print(f"Payload: {json.dumps(payload, indent=2)[:500]}")

        result_data = execute_task_sync(ttype, payload)

        report_result, _ = _mcp_http_call("tools/call", {"name": "report_result", "arguments": {
            "task_id": tid, "worker_id": WORKER_ID, "status": "completed", "result": result_data
        }}, sid)
        print(f"Result reported: {tid}")
    else:
        print("Claim: no tasks available")

    print("=== Tick complete ===")


def execute_task_sync(task_type, payload):
    """Execute a claimed task synchronously (for direct mode)."""
    if task_type == "linux-admin":
        commands = payload.get("commands", [])
        if isinstance(commands, list):
            outputs = []
            for cmd in commands:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                outputs.append({"command": cmd, "exit_code": r.returncode, "output": r.stdout[:500]})
            return json.dumps({"status": "completed", "results": outputs})
    elif task_type == "docker-maintenance":
        r = subprocess.run("docker ps -a --format '{{.ID}} {{.Status}} {{.Names}}' 2>&1",
                          shell=True, capture_output=True, text=True, timeout=15)
        return json.dumps({"status": "completed", "containers": r.stdout[:500]})
    elif task_type == "web-hosting":
        r1 = subprocess.run("systemctl is-active nginx 2>&1", shell=True, capture_output=True, text=True, timeout=10)
        r2 = subprocess.run("systemctl is-active apache2 2>&1", shell=True, capture_output=True, text=True, timeout=10)
        return json.dumps({"status": "completed", "nginx": r1.stdout[:200], "apache": r2.stdout[:200]})
    elif task_type == "nextcloud-support":
        r = subprocess.run("docker ps --filter name=nextcloud --format '{{.Names}} {{.Status}}' 2>&1",
                          shell=True, capture_output=True, text=True, timeout=10)
        return json.dumps({"status": "completed", "nextcloud": r.stdout[:500]})
    return json.dumps({"status": "completed", "message": f"Task {task_type} executed by {WORKER_ID}"})


# ── Bridge-mode MCP (async, uses mcp library) ───────────────────────

async def call_tool(session, name, args):
    result = await session.call_tool(name, args)
    texts = [c.text for c in result.content]
    raw = "".join(texts).strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def run_shell(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"exit_code": r.returncode, "stdout": r.stdout[:500], "stderr": r.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "timeout"}


async def execute_task(task_type, payload):
    """Execute a claimed task. Extend this with new task_type handlers."""
    if task_type == "linux-admin":
        commands = payload.get("commands", [])
        if isinstance(commands, list):
            outputs = []
            for cmd in commands:
                r = run_shell(cmd, timeout=30)
                outputs.append({"command": cmd, "exit_code": r["exit_code"], "output": r["stdout"][:500]})
            return {"status": "completed", "results": outputs}
    elif task_type == "docker-maintenance":
        r = run_shell("docker ps -a --format '{{.ID}} {{.Status}} {{.Names}}' 2>&1", timeout=15)
        return {"status": "completed", "containers": r["stdout"][:500]}
    elif task_type == "web-hosting":
        r1 = run_shell("systemctl is-active nginx 2>&1", timeout=10)
        r2 = run_shell("systemctl is-active apache2 2>&1", timeout=10)
        return {"status": "completed", "nginx": r1["stdout"][:200], "apache": r2["stdout"][:200]}
    elif task_type == "nextcloud-support":
        r = run_shell("docker ps --filter name=nextcloud --format '{{.Names}} {{.Status}}' 2>&1", timeout=10)
        return {"status": "completed", "nextcloud": r["stdout"][:500]}
    return {"status": "completed", "message": f"Task {task_type} executed by {WORKER_ID}"}


async def bridge_tick():
    """Full worker tick via mcp library (async, bridge mode)."""
    from mcp.client.streamable_http import streamable_http_client
    from mcp import ClientSession

    print(f"=== Worker {WORKER_ID} bridge tick ===")
    async with streamable_http_client(URL) as streams:
        read, write, get_sid = streams  # mcp>=1.26.0 3-tuple
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("MCP session initialized")

            hb = await call_tool(session, "heartbeat", {"worker_id": WORKER_ID})
            print(f"Heartbeat: {json.dumps(hb) if hb else 'OK'}")

            msgs = await call_tool(session, "read_messages", {
                "agent_id": WORKER_ID, "unread_only": True, "mark_read": True
            })
            if msgs and isinstance(msgs, list) and len(msgs) > 0:
                print(f"Messages ({len(msgs)}):")
                for m in msgs:
                    print(f"  - {json.dumps(m, indent=2)}")
            else:
                print("Messages: none unread")

            claim = await call_tool(session, "claim_task", {
                "worker_id": WORKER_ID, "task_types": TASK_TYPES
            })
            if claim and isinstance(claim, dict) and claim.get("id"):
                task_id = claim["id"]
                task_type = claim.get("type", "unknown")
                payload = claim.get("payload", {})
                print(f"\nTask claimed: {task_id} ({task_type})")
                print(f"Payload: {json.dumps(payload, indent=2)[:500]}")

                result = await execute_task(task_type, payload)

                report = await call_tool(session, "report_result", {
                    "task_id": task_id, "worker_id": WORKER_ID, "result": result
                })
                print(f"Report result: {json.dumps(report, indent=2)[:300]}")
            else:
                print("Claim: no tasks available")

    print("=== Tick complete ===")


# ── Entry point ──────────────────────────────────────────────────────

if __name__ == "__main__":
    healthy, reason = check_bridge()
    if healthy:
        # Detect bridge's agent ID to decide oversight vs direct mode
        bridge_agent = None
        try:
            r = subprocess.run(
                ["systemctl", "--user", "show", BRIDGE_SERVICE, "--property=Environment"],
                capture_output=True, text=True, timeout=10
            )
            for part in r.stdout.split():
                if part.startswith("AGENT_ID="):
                    bridge_agent = part.split("=", 1)[1].strip('"')
                    break
        except Exception:
            pass

        if bridge_agent and bridge_agent != WORKER_ID:
            # Different agent IDs — cron does its own MCP calls
            print(f"Bridge runs for {bridge_agent}, cron serves {WORKER_ID} — doing direct tick")
            direct_tick()
        else:
            # Same agent ID — bridge handles MCP loop, cron does oversight
            stale = check_stale_workers()
            if isinstance(stale, list) and stale:
                init_result, sid = _mcp_http_call("initialize", {
                    "protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": f"{WORKER_ID}-cron", "version": "1.0"}
                })
                if sid:
                    _mcp_http_call("notifications/initialized", {}, sid)
                    send_message_to_primary(sid, stale)
                    print(f"Stale workers reported: {json.dumps(stale, indent=2)}")
                else:
                    print(f"Stale workers detected but MCP init failed: {json.dumps(stale, indent=2)}")
            else:
                print(f"Bridge {BRIDGE_SERVICE} healthy — no stale workers")
        sys.exit(0)

    print(f"Bridge {BRIDGE_SERVICE} unhealthy: {reason}")
    print("Falling through to direct MCP HTTP mode...")
    direct_tick()
