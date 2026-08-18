# Official Docs First + Local Research Subagents

When investigating whether Hermes (or any tool in the network) supports a feature or has a best practice, follow this order:

1. **Check Hermes docs** at `https://hermes-agent.nousresearch.com/docs`.
   - Use `llms.txt` or `llms-full.txt` for quick search: `https://hermes-agent.nousresearch.com/docs/llms-full.txt`
   - Use `web_extract` on feature pages (mcp, cron, messaging, hooks, api-server).

2. **Check Hermes source code** if docs are silent or incomplete.
   - Clone `https://github.com/NousResearch/hermes-agent`
   - Search for the relevant term (`events_poll`, `gateway:startup`, `MessageEvent`, `cron/fire`, `mcp serve`).

3. **Dispatch a local research subagent** for thorough investigation.
   - Give it the exact docs URL, the source repo URL, and the specific question.
   - Ask it to report: what exists, what does not exist, and the recommended official approach.

4. **Only after (1)-(3) are exhausted** consider a custom bridge, hook, or workaround.

## Why this order matters

- Hermes evolves; a blog post or forum answer may be stale.
- The source code contains internal paths that are not stable APIs; relying on them creates breakage risk.
- Official mechanisms (cron, API server, `/api/cron/fire`) are supported and survive upgrades.
- A subagent can do parallel code+doc search without flooding the primary's context.

## Example questions that should go through this funnel

- "Can an MCP server push an event that wakes the agent?"
- "How do I make a skill auto-load by default?"
- "Can the gateway start a new turn from a Python script?"
- "What is the supported way to run a background agent process?"

For each, the research subagent should return a concise table: official approach, non-official internal approach, and recommendation.

## What to capture

- Link to the doc page or source file that answered the question.
- Exact code pointers when relevant (file:line ranges).
- A one-line bottom line suitable for quoting to the user.

---
*Captured from session 2026-06-21.*
