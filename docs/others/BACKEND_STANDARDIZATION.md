# Backend standardization: FastAPI migration

## Goal

Standardize HTTP APIs on FastAPI while preserving the existing browser
contracts, user access rules, and Socket.IO chat stream. The migration should
be incremental: keep the current service available while routes are moved and
verified, then remove Flask after no production traffic depends on it.

## Current state

- `server/app.py` creates the primary Flask application.
- `server/api/login.py`, `conversation.py`, and `ingest.py` define Flask
  blueprints.
- Flask-Login and Flask's signed session cookie authenticate the browser.
- Flask-SocketIO sends chat progress and answer frames on `chat-{chat_id}`.
- FastAPI is already used by the document extraction and ingestion
  microservices under `server/src/services/`.
- Standalone FastAPI chat and RAG applications now run alongside the monolith
  from a shared Docker image. They use bearer-token authentication and are
  migration entry points; the Flask browser/session and Socket.IO contracts
  remain owned by the compatibility server.
- A standalone FastAPI authentication service now issues bearer tokens and
  serves user/RBAC identity lookups for the Chat and RAG services. Authentication
  is database-only; LDAP support has been removed.
- The React client expects the current URL shapes, response bodies, cookie
  authentication, and Socket.IO event payloads.

## Target architecture

- FastAPI is the HTTP API framework for login, conversation, documents, health,
  and metrics endpoints.
- `python-socketio` `AsyncServer` and its `ASGIApp` provide Socket.IO on the
  same ASGI deployment as FastAPI.
- Uvicorn runs the ASGI application in local and container deployments.
- Shared application services (model manager, repositories, RAG, privacy,
  guardrails, and telemetry) are constructed once and injected through
  FastAPI's application state/dependencies.
- Existing URL paths and response shapes remain stable during the first
  migration; client changes are only made when required and separately
  validated.
- Authentication keeps the current browser session-cookie behavior during the
  migration. Do not silently switch to bearer tokens or change cookie
  semantics as part of a framework conversion.

## Migration phases

### Phase 1: ASGI runtime and compatibility harness

1. Define an application factory for the target FastAPI app and an async
   Socket.IO server.
2. Run the ASGI app with Uvicorn and verify health, CORS, error responses,
   telemetry, and Socket.IO connectivity.
3. Keep Flask routes available behind an explicit compatibility mount while
   route-by-route migration is in progress. Do not place duplicate FastAPI
   endpoints at paths still owned by Flask.
4. Add integration tests for the existing login cookie and authenticated
   calls through the ASGI entry point.

**Exit criteria:** both old clients and test clients can reach the compatibility
routes through the new ASGI process, and Socket.IO connections and event
frames continue to work.

### Phase 2: Authentication and authorization

1. Introduce a framework-neutral authentication service interface that
   resolves a request to the existing `User` model.
2. Implement FastAPI dependencies for required-user and upload-permission
   checks.
3. Preserve existing login/logout/current-user behavior and session expiry
   semantics while moving those endpoints.
4. Test unauthenticated responses, invalid credentials, cookie issuance,
   session expiry, permissions, logout invalidation, and CORS credentials.

**Exit criteria:** all callers use the FastAPI authentication dependencies;
Flask-Login is only used by routes that have not yet migrated.

### Phase 3: Chat and Socket.IO

1. Convert chat list/create/read/update/delete, feedback, and token endpoints
   while preserving their current paths and JSON shapes.
2. Convert chat invocation to a native async FastAPI endpoint. Remove the
   Flask `run_until_complete` bridge as part of this phase.
3. Replace Flask-SocketIO emits with `AsyncServer.emit`, preserving the
   `chat-{chat_id}` channel, `agent-action` payloads, and answer chunk behavior.
4. Inject the authenticated user and chat repositories using dependencies.
5. Add API tests for access isolation, all supported workflows/providers,
   output guardrail blocks, PII redaction, and streaming/final-response
   compatibility.

**Exit criteria:** the React chat and Ask flows work against FastAPI without
client contract regressions.

### Phase 4: Document routes

1. Convert upload, list, page-read, bucket-list, and delete routes to FastAPI.
2. Preserve multipart field names, file validation, visibility-group
   enforcement, and Temporal-orchestrated extraction/ingestion.
3. Use async file handling or bounded thread-pool work for blocking
   filesystem/network operations; do not block the ASGI event loop.
4. Add tests for upload permissions, duplicates, quota enforcement, partial
   failures, and document visibility.

**Exit criteria:** no document API traffic depends on Flask.

### Phase 5: Remove Flask

1. Confirm all routes, authentication, error handlers, CORS, telemetry, and
   real-time events run on the ASGI stack.
2. Remove Flask, Flask-CORS, Flask-Login, and Flask-SocketIO dependencies and
   Flask-specific middleware.
3. Update Docker and local startup commands to run Uvicorn.
4. Remove the compatibility mount and the remaining Flask application.
5. Run full backend tests, frontend build, container configuration checks,
   and an end-to-end smoke test against PostgreSQL, Neo4j, object storage,
   and the configured model provider.

**Exit criteria:** FastAPI and ASGI are the only backend web runtime.

## Cross-cutting requirements

- Preserve user authorization checks for every read/write path. In particular,
  document retrieval must continue to filter by the user's groups.
- Keep PII redaction before model use, response delivery, logging, and
  telemetry export.
- Keep NeMo input/output guardrails around the chat request and generated
  answer.
- Avoid sending prompts, completions, PII, cookies, tokens, or user/chat IDs as
  telemetry attributes.
- Maintain the current frontend wire protocol until explicit client changes
  are coordinated.
- Never run synchronous database, filesystem, model, or third-party calls
  directly on the ASGI event loop; use async clients or bounded thread pools.
- Keep service construction injectable so endpoint tests do not require live
  databases or model credentials.

## Important implementation notes

- Do not assume that mounting Flask under ASGI completes the migration. It is
  only a temporary compatibility mechanism; its routes remain Flask routes
  until rewritten.
- Flask's signed session cookie and Flask-Login's user loading behavior must
  be deliberately retained or replaced. FastAPI does not automatically
  understand them.
- Socket.IO is a separate protocol from ordinary WebSockets. The migration
  should use `python-socketio`'s ASGI integration rather than replacing the
  existing events with raw FastAPI WebSockets.
- The server Docker command currently starts `python app.py`; the final ASGI
  runtime should start Uvicorn against the new application factory.
- Temporal support is independent of the web-framework migration and remains
  an opt-in adapter until its application-specific activity and worker are
  deployed.

## Suggested order of implementation

Implement Phase 1 and the authentication tests before migrating route groups.
Then migrate authentication, chat, and document endpoints in separate
reviewable changes. Keep the compatibility application enabled until each
route group has parity and the client smoke tests pass. Remove Flask only in
the final phase.
