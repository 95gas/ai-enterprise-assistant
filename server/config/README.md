# Backend configuration

`settings.py` provides one typed `Settings` object to the Flask app and all
FastAPI services. It loads the YAML files in this directory, validates the
values with Pydantic, and lets environment variables override the YAML
defaults. Malformed YAML and invalid setting values fail during startup.

## Pipeline files

| File | Settings |
|---|---|
| `system.yaml` | Active theme label, HTTP port, device, and allowed origins. |
| `chat.yaml` | Chat history and notes limits. |
| `ingestion.yaml` | Chunking, date formatting, and private-document limits. |
| `models.yaml` | Selected chat, embedding, helper, document, and vision models. The defaults use a local Hugging Face chat model and Sentence Transformers embedder for demos. |
| `users.yaml` | Default account limits and configured groups/permissions. |
| `tickets.yaml` | Ticket categories and allowed values used by the support workflow. |
| `storage.yaml` | Shared S3 folder structure and optional local document path. |
| `microservices.yaml` | Shared task TTL and service execution settings. |
| `prompts.yaml` | Prompt substitution keys and streamed progress text. |
| `guardrails/config.yml` | NeMo Guardrails' own model and rail configuration. |

Use the closest pipeline file for a setting; keep credentials and other
environment-specific values out of YAML. Add a new YAML file to
`PIPELINE_CONFIGS` in `settings.py` when adding a new settings domain.

## Secrets and overrides

Copy `server/config/secrets.env.example` to `server/config/secrets.env` for
local development. This is the single shared environment file for Docker
Compose and locally launched services. PostgreSQL uses `POSTGRES_HOST`,
`POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`; the
application builds its connection URL from those values, using `localhost`
locally and Compose's `postgres` hostname in containers. The file is ignored
by Git and Docker build contexts. In production, inject credentials through
the orchestrator's secret manager instead of baking them into an image.

For an existing setup, migrate non-empty values from `docker/.env` into
`server/config/secrets.env`. Docker Compose no longer reads `docker/.env`.

The example's PostgreSQL, Neo4j, S3, and JWT values are local-demo defaults,
not secure deployment credentials.

The checked-in model selection is also a local demo configuration:
`google/gemma-3-270m-it` for chat/helper/document generation and
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` for
384-dimensional embeddings. Gemma's Hugging Face repository requires accepting
Google's model terms while signed in; set `HUGGINGFACE_API_TOKEN` in
`server/config/secrets.env` after accepting them. Model weights are downloaded on first use
and cached by Hugging Face.

Process environment variables override the shared env file. For example,
`POSTGRES_HOST`, `NEO4J_PASSWORD`, and `OPENROUTER_API_KEY` can be set directly.
`THEME` selects an optional prompt asset subdirectory; it no longer selects a
nested deployment configuration tree.

Google service-account credentials are supplied as a local
`google_credentials.json` file or by setting
`GOOGLE_CREDENTIALS_PATH` to an externally mounted file. The file is ignored
by Git and Docker build contexts. For Compose deployments, mount the credential
read-only into each service that needs it and set `GOOGLE_CREDENTIALS_PATH` to
that in-container path using a Compose override; never add the credential to
the image.
