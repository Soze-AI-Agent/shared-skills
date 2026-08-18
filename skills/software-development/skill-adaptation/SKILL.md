---
name: skill-adaptation
description: Convert a non-Hermes skill (Claude Code CLAUDE.md, Codex, Gemini, custom format) into a Hermes-compatible SKILL.md and install it locally or network-wide.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [skills, hermes-agent, claude-code, codex, porting, adaptation, SKILL.md]
    related_skills: [hermes-agent-skill-authoring, agent-network-coordination]
---

# Skill Adaptation — Port External Agent Skills to Hermes

Convert a skill written for another agent framework (Claude Code `CLAUDE.md`, Codex CLI, Gemini, OpenCode, etc.) into a Hermes-compatible `SKILL.md` that can be loaded by the local Hermes instance or distributed to a network of agents.

## When to use

- The user points to a skill repo from another agent ecosystem (e.g. `JuliusBrussee/caveman`) and asks you to make it work in Hermes.
- You need to install an external skill so it is active by default in Hermes.
- You want to push a skill to multiple Hermes agents over a knowledge base or Task Bus.

## Core differences

| Framework | Default persona file | Skill format | Load location |
|---|---|---|---|
| **Claude Code** | `CLAUDE.md` | Markdown system prompt | Repo root or `.claude/CLAUDE.md` |
| **Codex CLI** | `CODEX.md` | Markdown system prompt | Repo root or `.codex/CODEX.md` |
| **Gemini CLI** | `GEMINI.md` | Markdown system prompt | Repo root |
| **Hermes** | `~/.hermes/SOUL.md` | `SKILL.md` with YAML frontmatter | `~/.hermes/skills/<category>/<name>/SKILL.md` |

Hermes skills are **not** just prompts. They have:
- YAML frontmatter (`name`, `description`, etc.)
- A markdown body with sections like `## When to use`, `## Common pitfalls`, `## Verification checklist`
- Optional `references/`, `templates/`, and `scripts/` directories

## Workflow

### 1. Fetch the upstream skill content

Use `web_extract` on the repo's README, the persona file (`CLAUDE.md`, `CODEX.md`, etc.), and any `SKILL.md` if it already exists.

```
https://raw.githubusercontent.com/<owner>/<repo>/main/CLAUDE.md
https://raw.githubusercontent.com/<owner>/<repo>/main/README.md
https://raw.githubusercontent.com/<owner>/<repo>/main/skills/<skill>/SKILL.md
```

### 2. Decide how Hermes should load it

Two options:

| Goal | Approach |
|---|---|
| Apply the persona/tone to every session | Edit `~/.hermes/SOUL.md` |
| Make it a toggleable skill with triggers | Create `~/.hermes/skills/<category>/<name>/SKILL.md` |

For a communication style like caveman, do **both**:
- Put the persona text in `~/.hermes/SOUL.md` so it is active immediately.
- Create a skill so the rules are documented and can be distributed to other agents.

### 3. Build the Hermes SKILL.md

Required frontmatter (source of truth: `hermes-agent-skill-authoring`):

```yaml
---
name: <lowercase-hyphenated-name>
description: Use when <trigger>. <one-line behavior>.  # ≤ 1024 chars
version: 1.0.0
author: Hermes Agent (adapted from <source>)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [<tags>]
    related_skills: [<related>]
---
```

Then add the adapted body:
- `## When to use` — triggers
- `## Rules` — the actual behavior rules
- `## Intensity / variants` — if the original had levels or modes
- `## Auto-Clarity` — exceptions where the style drops
- `## Boundaries` — when to disable or revert
- `## Verification checklist`

Keep exact technical terms, code, API names, and error strings verbatim. Drop the original framework's voice but preserve the substance.

### 4. Validate the skill locally

```python
import yaml, pathlib
content = pathlib.Path("~/.hermes/skills/<category>/<name>/SKILL.md").expanduser().read_text()
assert content.startswith("---")
fm = yaml.safe_load(content.split("\n---\n", 1)[0])
assert "name" in fm and "description" in fm
assert len(fm["description"]) <= 1024
assert len(content) <= 100_000
```

### 5. Install locally

```bash
mkdir -p ~/.hermes/skills/<category>/<name>
cp SKILL.md ~/.hermes/skills/<category>/<name>/SKILL.md
```

If the skill also needs a persona, update `~/.hermes/SOUL.md`.

### 6. Restart Hermes gateway

Skills are loaded at session startup. Restart from a separate shell:

```bash
systemctl --user restart hermes-gateway.service
```

A gateway cannot safely restart itself from inside itself.

### 7. Distribute network-wide (optional)

1. Place the skill under a knowledge base repo's `skills/<name>/` directory.
2. Add a `README.md` explaining install steps.
3. Push to the knowledge base.
4. Submit a `linux-admin` task to each worker to copy the files and restart.
5. Track completion with `list_tasks(status="done")`.

## Common pitfalls

- **Copying a `CLAUDE.md` directly into `~/.hermes/skills/`.** Hermes ignores it unless it is a proper `SKILL.md` with YAML frontmatter.
- **Forgetting to set a global persona.** A skill only loads when invoked or matched by trigger. For always-on style, use `~/.hermes/SOUL.md`.
- **Description over 1024 chars.** The skill validator rejects it. Keep the description short and trigger-focused.
- **Skipping the restart.** New skills are not visible until the next Hermes session.
- **Trying to restart the gateway from inside itself.** The CLI blocks this because it would kill the running session. Restart from an external shell or schedule a background process.

## Verification checklist

- [ ] Upstream persona/skill content fetched and reviewed
- [ ] Hermes `SKILL.md` created with valid frontmatter
- [ ] Skill installed at `~/.hermes/skills/<category>/<name>/SKILL.md`
- [ ] Global persona updated in `~/.hermes/SOUL.md` if needed
- [ ] Gateway restarted from an external shell
- [ ] New skill appears in `hermes skills list` or a fresh session
- [ ] Knowledge base copy pushed if distributing to workers
- [ ] Workers receive install task and report `done`

## References

- `hermes-agent-skill-authoring` — official SKILL.md structure and validator rules
- `agent-network-coordination` — how to push skills/config to multiple agents via the Task Bus
- `references/caveman-hermes-example.md` — concrete worked example of porting a communication-style skill
