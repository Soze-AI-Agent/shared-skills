#!/usr/bin/env python3
"""
Shared Skills Sync — pull skills from central git repo to local ~/.hermes/skills/

Usage:
    sync-skills.py pull       # fetch latest skills from repo
    sync-skills.py push       # commit local changes and push
    sync-skills.py status     # show sync state (local vs remote)

Env:
    SKILLS_REPO_URL    git remote URL (default: uses origin from ~/.hermes/skills/)
    SKILLS_LOCAL_DIR   local skills dir (default: ~/.hermes/skills)
    SKILLS_REPO_DIR    temp clone dir (default: /tmp/shared-skills)

Returns 0 on success, 1 on conflicts needing manual resolution.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILLS_LOCAL_DIR = Path(os.getenv("SKILLS_LOCAL_DIR", str(Path.home() / ".hermes" / "skills")))
SKILLS_REPO_DIR = Path(os.getenv("SKILLS_REPO_DIR", "/tmp/shared-skills"))
SKILLS_REPO_URL = os.getenv("SKILLS_REPO_URL", "")


def run(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        print(f"error: {r.stderr.strip()}")
        sys.exit(1)
    return r


def ensure_repo():
    """Clone or pull the shared skills repo."""
    if not SKILLS_REPO_URL:
        print("error: SKILLS_REPO_URL not set")
        sys.exit(1)
    if SKILLS_REPO_DIR.exists():
        shutil.rmtree(SKILLS_REPO_DIR, ignore_errors=True)
    run(f"git clone --depth 1 {SKILLS_REPO_URL} {SKILLS_REPO_DIR}")


def pull():
    """Pull remote skills into local skills dir."""
    ensure_repo()
    SKILLS_LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    remote_skills = SKILLS_REPO_DIR / "skills"
    if not remote_skills.exists():
        print("warn: no skills/ dir in remote repo")
        return 0

    # Sync: copy files from remote that are newer or don't exist locally
    updated = []
    for src in remote_skills.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(remote_skills)
        dst = SKILLS_LOCAL_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            shutil.copy2(src, dst)
            updated.append(str(rel))

    if updated:
        print(f"synced {len(updated)} skill(s):")
        for u in updated:
            print(f"  + {u}")
    else:
        print("up to date")
    return 0


def push():
    """Push local skills changes to remote repo."""
    if not SKILLS_REPO_URL:
        print("error: SKILLS_REPO_URL not set")
        sys.exit(1)
    ensure_repo()
    local_skills = SKILLS_LOCAL_DIR
    remote_skills = SKILLS_REPO_DIR / "skills"
    remote_skills.mkdir(parents=True, exist_ok=True)

    # Copy local to temp repo
    changes = []
    for src in local_skills.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(local_skills)
        dst = remote_skills / rel
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            changes.append(str(rel))

    if not changes:
        print("no local changes to push")
        return 0

    run("git add -A", cwd=SKILLS_REPO_DIR)
    run(f'git commit -m "sync: update {len(changes)} skill(s)"', cwd=SKILLS_REPO_DIR, check=False)
    run(f"git push origin master", cwd=SKILLS_REPO_DIR)
    print(f"pushed {len(changes)} change(s)")
    return 0


def status():
    """Show current sync state."""
    print(f"local dir:  {SKILLS_LOCAL_DIR}")
    print(f"repo dir:   {SKILLS_REPO_DIR}")
    print(f"repo URL:   {SKILLS_REPO_URL or '(not set)'}")
    print(f"local files: {sum(1 for _ in SKILLS_LOCAL_DIR.rglob('*') if _.is_file())}")
    if SKILLS_REPO_DIR.exists():
        remote_count = sum(1 for _ in (SKILLS_REPO_DIR / "skills").rglob("*") if _.is_file())
        print(f"remote files: {remote_count}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {
        "pull": pull,
        "push": push,
        "status": status,
    }.get(cmd, status)()
