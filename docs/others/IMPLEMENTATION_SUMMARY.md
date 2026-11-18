# Implementation Summary

This document records the code and configuration changes made for the RAG,
guardrails, observability, agent streaming, Temporal, and MCP work.

## Privacy and content guardrails

- Added a Presidio analyzer/anonymizer wrapper with configurable language,
  spaCy model, and replacement text.
- Added recursive response redaction, including nested structures and Pydantic
  models.
- Redacted incoming questions, prior conversation context, generated output,
  MCP arguments/results, error messages, and application log content before
  they are persisted, returned, streamed, or exported.
- Added optional NeMo Guardrails input and output checks. Guardrail-blocked
  chat requests receive a generic HTTP 403 response; modified content is
  redacted before subsequent use.
- Added bundled NeMo self-check input/output rail configuration.
- Added the Presidio, spaCy model, and NeMo dependencies and configured the
  server image to install the model.

Configuration:

- `PRESIDIO_LANGUAGE` (default `en`)
- `PRESIDIO_SPACY_MODEL` (default `en_core_web_sm`)
- `PRESIDIO_REDACTION_TEXT` (default `<REDACTED>`)
- `NEMO_GUARDRAILS_ENABLED` (default `false`)
- `NEMO_GUARDRAILS_CONFIG` (defaults to the bundled configuration)

## Agent streaming and chat workflow

- Added typed agent progress events and forwarded safe progress summaries on
  the existing `chat-{id}` Socket.IO channel using the `agent-action` frame
  shape.
- Stored progress action frames with response metadata for the persisted chat
  trace.
- Buffered generated text until output guardrails and PII redaction have run,
  then emitted it in chunks.
- Connected progress frames to the existing frontend action/reasoning row in
  chat and Ask views.
- Refactored workflow selection into a mapping and added backend mappings for
  the frontend's `General` and `DeepResearch` workflow values.
- Added request validation for supported workflow and provider values.
- Improved dependency injection in the application factory and agent setup.

## RAG and tests

- Extracted parameterized RAG filter construction into a helper.
- Corrected the page-number filter to bind the expected query parameter.
- Added tests for filter construction, including optional filters.
- Added focused tests for Presidio redaction, NeMo behavior, MCP allowlisting
  and authentication, Temporal opt-in behavior, and telemetry sanitization.

## Observability

- Added opt-in OpenTelemetry tracing and metrics for chat duration, request and
  error counts, token usage, and RAG retrieval latency/results.
- Sanitized HTTP path and query attributes to avoid exporting user/chat
  identifiers or request query values as trace attributes.
- Added a Prometheus `/metrics` endpoint when telemetry is enabled.
- Forwarded application logs through OTLP after redaction.
- Added an optional Docker Compose observability profile with an OTel
  Collector, Prometheus, Tempo, Loki, Grafana provisioning, and an ASK runtime
  dashboard.

Configuration:

- Set `OTEL_ENABLED=true` to enable application telemetry.
- Set `OTEL_SERVICE_NAME` and `OTEL_EXPORTER_OTLP_ENDPOINT` as needed.
- Start the Compose stack with `--profile observability` to run the monitoring
  services.
- Set `GRAFANA_ADMIN_PASSWORD` to a non-default secret before exposing Grafana.

## MCP tools

- Added a streamable-HTTP MCP client for the ResearchAgent.
- Exposed only tools explicitly named in each server's `allowed_tools` list.
- Added configurable bearer-token authentication through a named environment
  variable, request timeouts, and redaction of tool arguments and results.

Configuration is supplied as a JSON list in `MCP_SERVERS_JSON`. Each server
entry requires a unique `name`, HTTP(S) `url`, and explicit `allowed_tools`;
`token_env` can name an environment variable containing its bearer token.

## Temporal

- Added document-ingestion, extraction, and batch-deletion workflows with
  activities that invoke Markdown Maker and Markdown Ingestor.
- Wired both the RAG upload API and Flask compatibility upload route to the
  Temporal ingestion workflow; mixed fast/full batches are split by mode.
- Added a standalone Temporal worker service and Compose services for the
  Temporal server, Markdown Maker, and Markdown Ingestor.
- Moved the Markdown service packages into `server/src/services/`, moved the
  Chat/RAG FastAPI entry points into their matching service packages, and
  removed the duplicate microservice manager app.

The separate chat agent-loop adapter is still not wired into the synchronous
Socket.IO chat request path.

Configuration:

- `TEMPORAL_ENABLED`
- `TEMPORAL_ADDRESS` (default `localhost:7233`)
- `TEMPORAL_NAMESPACE` (default `default`)
- `TEMPORAL_MICROSERVICES_TASK_QUEUE` (default `ask-microservices`)
- `MD_MAKER_URL` (default `http://localhost:8005`)
- `MD_INGESTOR_URL` (default `http://localhost:8006`)
- `TEMPORAL_ACTIVITY_TIMEOUT_SECONDS` (default `900`)

## Documentation and deployment

- Updated the README with setup and configuration guidance for redaction,
  NeMo Guardrails, telemetry, MCP, and the Temporal adapter.
- Updated the server Docker image and Compose configuration for the required
  packages, model setup, server startup, and optional monitoring services.
- Added configuration and dashboard assets under `docker/observability/` and
  bundled guardrail configuration under
  `server/config/guardrails/config.yml`.

## Verification

- Backend test suite: **18 passed**.
- Python compilation: passed.
- Docker Compose observability configuration validation: passed.
- Frontend TypeScript check and production build: passed.

The frontend build reports an existing outdated Browserslist database warning
and a large-chunk size warning. External integration packages were not
runtime-tested against live services in this environment; the configuration,
unit-level behavior, and application integration points were validated locally.
