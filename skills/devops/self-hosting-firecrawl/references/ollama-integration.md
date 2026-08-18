# Integrating a local Ollama endpoint with self-hosted Firecrawl

## Goal

Enable Firecrawl's AI features (deprecated `/v1/extract` and any other endpoint
that calls the configured LLM) to use a local Ollama instance instead of OpenAI.

## What to set in `.env`

```
OLLAMA_BASE_URL=http://host.docker.internal:11434/api
MODEL_NAME=<model-name>
# Optional:
MODEL_EMBEDDING_NAME=nomic-embed-text
```

`host.docker.internal` resolves to the Docker bridge gateway (`172.17.0.1`) if
your `docker-compose.yaml` includes the standard `extra_hosts` entry. The
Firecrawl upstream compose file already adds:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

## Verify Ollama is reachable from the Firecrawl container

```bash
docker exec firecrawl-api-1 curl -s http://host.docker.internal:11434/api/version
```

Expected output:
```json
{"version":"0.30.7"}
```

## Picking a model

The self-hosted Firecrawl image currently logs a warning like:

```
No pricing information found for model: <name>
```

This is harmless for local use but indicates the image does not have a built-in
pricing table entry for that model. Extraction still works. Choose any pulled
Ollama model that supports chat completions:

- `llama3.2`
- `gemma4:31b-cloud`
- `qwen3.5:397b-cloud`

Use the model name exactly as `ollama list` reports it.

## Working extraction endpoint

At the time this reference was written, the newer `/v2/scrape` JSON-extraction
options (`jsonOptions`, `extract`, etc.) were rejected by the self-hosted image.
The deprecated `/v1/extract` endpoint worked with the local Ollama backend:

```bash
curl -X POST http://primary.tail298a48.ts.net:3002/v1/extract \
  -H 'Content-Type: application/json' \
  -d '{
    "urls": ["https://example.com"],
    "prompt": "Extract the page title and main heading as JSON with keys title and heading.",
    "schema": {
      "type": "object",
      "properties": {"title": {"type": "string"}, "heading": {"type": "string"}}
    }
  }'
```

Expected response:
```json
{"success": true,
 "data": {"title": "Example Domain", "heading": "Example Domain"},
 ...
}
```

## Restart after changing `.env`

```bash
cd ~/firecrawl
docker compose down
docker compose up -d
```

Then confirm inside the container that the variables are set:

```bash
docker exec firecrawl-api-1 env | grep -E 'OLLAMA|MODEL'
```

## Caveats

- `/v2/scrape` AI extraction fields may differ in newer or older Firecrawl image
tags. If `/v1/extract` is removed in a future image, retest the v2 body fields
against the running container.
- `host.docker.internal` only works when Ollama is bound to `0.0.0.0:11434` (the
  default on most Linux installs). If Ollama only listens on `127.0.0.1`, expose
  it with `OLLAMA_HOST=0.0.0.0:11434 ollama serve` and restart Ollama.
- No API key is required for self-hosted Firecrawl when
  `USE_DB_AUTHENTICATION=false`.
