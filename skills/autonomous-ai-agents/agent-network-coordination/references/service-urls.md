# Network Canonical URLs and Accounts

| Item | Value |
|---|---|
| Primary Tailscale hostname | `primary.tail298a48.ts.net` |
| Primary Tailscale IP | `100.99.71.23` |
| Task Bus MCP endpoint | `http://primary.tail298a48.ts.net:8765/mcp` |
| Task Bus SSE endpoint | `http://primary.tail298a48.ts.net:8765/sse` |
| Firecrawl endpoint | `http://primary.tail298a48.ts.net:3002` |
| Knowledge base repo | `https://github.com/Soze-AI-Agent/Soze-AI-Agents-KnowledgeBase` |
| GitHub account | `Soze-AI-Agent` |
| GitHub email | `sozeaiagent@gmail.com` |
| Primary worker ID | `primary` |

## Notes

- Services bind to the Tailscale IP only, not `0.0.0.0`.
- Firecrawl has DB authentication disabled for internal tailnet use.
- GitHub PAT is stored in `~/.git-credentials` and exported as `GITHUB_TOKEN`.
