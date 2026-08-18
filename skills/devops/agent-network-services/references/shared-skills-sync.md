# Shared Skills Sync — Git-Based Centralized Skill Distribution

One agent learns → all agents gain the skill. Distributed Hermes agents share a single
skill library via git, synced every 15 minutes.

## Why git

| Approach | Verdict |
|---|---|
| **Git** ✅ | Version control, conflict resolution, offline capable, audit trail |
| NFS mount | Single point of failure, no versioning |
| Nostr/Buzz events | Overkill for file sync, adds complexity |
| Task Bus | Wrong abstraction; file sync needs git semantics |

## Architecture

```
GitHub: Soze-AI-Agent/shared-skills (or primary-hosted Gitea)
├── skills/<category>/<name>/SKILL.md
├── skills/<category>/<name>/references/
├── skills/<category>/<name>/scripts/
└── scripts/sync-skills.py

Each agent:
  ~/.hermes/skills/          ← local skill library (live)
  ~/.hermes/scripts/sync-skills.py  ← sync script
  cron every 15m: pull from remote → copy to local
```

## Sync script (~/.hermes/scripts/sync-skills.py)

```python
#!/usr/bin/env python3
"""Pull skills from central git repo to ~/.hermes/skills/"""
import os, shutil, subprocess, sys
from pathlib import Path

LOCAL = Path.home() / ".hermes" / "skills"
REPO = Path("/tmp/shared-skills")
REMOTE = os.getenv("SKILLS_REPO_URL", "")

def run(cmd, cwd=None):
    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"error: {r.stderr.strip()}")
        sys.exit(1)
    return r

def pull():
    if not REMOTE:
        print("error: SKILLS_REPO_URL not set"); sys.exit(1)
    if REPO.exists():
        shutil.rmtree(REPO)
    run(f"git clone --depth 1 {REMOTE} {REPO}")
    LOCAL.mkdir(parents=True, exist_ok=True)
    remote = REPO / "skills"
    if not remote.exists():
        print("warn: no skills/ dir in repo"); return
    updated = []
    for src in remote.rglob("*"):
        if src.is_dir(): continue
        rel = src.relative_to(remote)
        dst = LOCAL / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            shutil.copy2(src, dst); updated.append(str(rel))
    print(f"synced {len(updated)} skill(s)" if updated else "up to date")

if __name__ == "__main__":
    pull()
```

## Cron job (on every agent)

```python
cronjob(
    action="create",
    name="skills-sync",
    schedule="*/15 * * * *",
    script="sync-skills.py",
    no_agent=True,
    deliver="local",
)
```

## Conflict rule

**Remote wins.** If local skill was modified more recently than last sync, the remote
copy overwrites it. Conflicts are reported to user, not auto-resolved.

Agents should NOT hand-edit skills directly — edit in the shared repo and let sync
propagate. The primary coordinator reviews and merges skill PRs.

## Push flow (when agent creates a new skill)

1. Agent writes skill to `~/.hermes/skills/<category>/<name>/`
2. Agent commits to shared repo and pushes
3. All other agents pull on next cron tick (~15 min max latency)

## Deployment to new agent

```bash
# On primary: init shared repo
cd /home/m/shared-skills
git init
git remote add origin https://github.com/Soze-AI-Agent/shared-skills.git

# On each agent:
scp primary:/home/m/shared-skills/scripts/sync-skills.py ~/.hermes/scripts/
# Set SKILLS_REPO_URL env, create cron
```

## Pitfalls

| Symptom | Fix |
|---|---|
| Skills not syncing | Check `SKILLS_REPO_URL` env var set; verify git clone works |
| Local edits lost | Remote wins — don't hand-edit skills locally, edit in repo |
| Cron not firing | Hermes cron syntax: positional schedule, not `--schedule` |
