# Git-only PAT setup recipe (headless / no gh)

Use this when `gh` is not installed and you want HTTPS git + curl API access with a personal access token.

## Steps

1. Obtain a classic PAT from https://github.com/settings/tokens with at least the `repo` scope (add `workflow` and `read:org` as needed).

2. Configure git to store credentials persistently and set commit identity:

   ```bash
   git config --global credential.helper store
   git config --global user.name "Hermes Agent"
   git config --global user.email "hermes@local"
   ```

3. Store the token in `~/.git-credentials` in the form:

   ```
   https://<github-username>:<PAT>@github.com
   ```

   Set mode `600` on the file.

4. Export `GITHUB_TOKEN` for API calls. Add to both `~/.bashrc` and `~/.hermes/.env` so it is available to future shells and Hermes sessions:

   ```bash
   echo 'export GITHUB_TOKEN=<PAT>' >> ~/.bashrc
   mkdir -p ~/.hermes
   echo 'GITHUB_TOKEN=<PAT>' >> ~/.hermes/.env
   ```

5. Verify:

   ```bash
   git ls-remote https://github.com/octocat/Hello-World.git
   source ~/.bashrc
   curl -s -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user
   ```

## Extracting the stored token

If credentials are already in `~/.git-credentials` but `GITHUB_TOKEN` is not set:

```bash
export GITHUB_TOKEN=$(grep "github.com" ~/.git-credentials | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|')
```

## Security note

`credential.helper store` saves the token in plaintext. On shared or high-security machines, prefer `credential.helper cache --timeout=28800` or use SSH keys instead.
