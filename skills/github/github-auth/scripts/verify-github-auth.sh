#!/usr/bin/env bash
# verify-github-auth.sh — quick GitHub auth check for agent accounts.
# Saves a few typed commands when confirming PAT + identity are wired.
set -euo pipefail

: "${GITHUB_TOKEN:?GITHUB_TOKEN is not set}"

printf 'Git identity: %s <%s>\n' "$(git config --global user.name)" "$(git config --global user.email)"
printf 'API user: %s\n' "$(curl -s -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user | python3 -c 'import sys,json; print(json.load(sys.stdin).get("login","?"))')"
git ls-remote https://github.com/Soze-AI-Agent/openclaw.git >/dev/null && echo 'git HTTPS access: OK'
