# Network-Wide Caveman Skill

Install this skill on every agent in the Soze AI agent network if you want terse, token-efficient caveman-style responses by default.

---

## Install

1. Copy `skills/caveman/SKILL.md` into your Hermes skills directory:

   ```bash
   mkdir -p ~/.hermes/skills/software-development/caveman
   cp skills/caveman/SKILL.md ~/.hermes/skills/software-development/caveman/SKILL.md
   ```

2. (Optional but recommended) Apply the same persona globally by overwriting `~/.hermes/SOUL.md` with the caveman persona from the same skill.

3. Restart your Hermes gateway to load the skill.

4. Test: ask a question. Responses should be terse but technically complete.

---

## Disable

Say any of:

- `"stop caveman"`
- `"normal mode"`
- `"disable caveman"`

---

## Notes

- Code blocks and exact error strings remain unchanged.
- Caveman auto-clarity kicks in for security warnings, irreversible actions, and ambiguous multi-step instructions.
- This is a Hermes adaptation of the original `JuliusBrussee/caveman` skill.
