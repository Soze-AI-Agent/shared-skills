# Caveman Skill — Hermes Adaptation Example

This is the concrete worked example referenced by the `skill-adaptation` skill. It shows how the caveman communication-style skill from `JuliusBrussee/caveman` was ported to Hermes.

## Source material

- Repo: `https://github.com/JuliusBrussee/caveman`
- Original files consulted:
  - `README.md` — overview and intensity levels
  - `CLAUDE.md` — persona text for Claude Code
  - `skills/caveman/SKILL.md` — existing skill format

## What was adapted

| Original | Hermes equivalent |
|---|---|
| `CLAUDE.md` persona block | `~/.hermes/SOUL.md` global persona |
| `skills/caveman/SKILL.md` | `~/.hermes/skills/software-development/caveman/SKILL.md` |
| Trigger keywords (`caveman mode`, `/caveman`) | Kept in `## When to use` |
| Intensity levels (lite/full/ultra/wenyan-*) | Kept in a table |
| Auto-clarity exceptions | Kept in `## Auto-Clarity` |
| Code-commits write normal | Kept in `## Boundaries` |

## Resulting files

- `~/.hermes/skills/software-development/caveman/SKILL.md`
- `~/.hermes/SOUL.md` — overwritten with caveman persona
- `Soze-AI-Agents-KnowledgeBase/skills/caveman/SKILL.md` — network-wide copy
- `Soze-AI-Agents-KnowledgeBase/skills/caveman/README.md` — install instructions for workers

## Commands used

```bash
# Create Hermes skill locally
mkdir -p ~/.hermes/skills/software-development/caveman
# (wrote SKILL.md with YAML frontmatter)

# Apply global persona
cat > ~/.hermes/SOUL.md <<'EOF'
# Hermes Agent Persona
> Caveman-style responses by default...
EOF

# Distribute to knowledge base
mkdir -p Soze-AI-Agents-KnowledgeBase/skills/caveman
cp ~/.hermes/skills/software-development/caveman/SKILL.md Soze-AI-Agents-KnowledgeBase/skills/caveman/
git add skills/caveman/
git commit -m "Add network-wide caveman skill"
git push origin main
```

## How workers install it

```bash
git clone https://github.com/Soze-AI-Agent/Soze-AI-Agents-KnowledgeBase.git
mkdir -p ~/.hermes/skills/software-development/caveman
cp Soze-AI-Agents-KnowledgeBase/skills/caveman/SKILL.md ~/.hermes/skills/software-development/caveman/SKILL.md
# Optionally update ~/.hermes/SOUL.md from the persona section
systemctl --user restart hermes-gateway.service
```

## Lessons

- Hermes `SKILL.md` needs YAML frontmatter; a raw persona file is ignored as a skill.
- A communication-style skill needs both a `SKILL.md` (so it is documented/distributable) and a `SOUL.md` entry (so it is active by default).
- Gateway restart must come from outside the running Hermes session.
- Workers may not understand custom `task_type` strings; use `linux-admin` with explicit `commands` for broad compatibility.
