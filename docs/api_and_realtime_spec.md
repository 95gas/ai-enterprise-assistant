# API Reference & Real-Time Streaming Protocol

The external REST surface is exposed by the FastAPI Gateway (`server/app.py`) through three primary API modules located in `server/api/`: `login.py`, `conversation.py`, and `ingest.py`. Real-time token streaming and multi-agent trace updates are delivered over WebSockets.

---

## Authentication & Authorization Headers

All endpoints except `/login` require a valid Bearer JWT issued by the Authentication Service (`server/src/services/authentication/`):

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

---

## 1. Authentication API (`server/api/login.py`)

### `POST /login`
Authenticates a user against either the local PostgreSQL user store or enterprise LDAP (`services/authentication/ldap.py`) and returns a signed JWT.

- **Request Body**:
  ```json
  {
    "username": "j.doe",
    "password": "••••••••••••"
  }
  ```
- **Response (`200 OK`)**:
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "user": {
      "id": "usr_98a7bc12",
      "username": "j.doe",
      "email": "j.doe@enterprise.com",
      "roles": ["user", "analyst"]
    }
  }
  ```
- **Error Responses**: `401 Unauthorized` (invalid credentials), `403 Forbidden` (disabled account), `502 Bad Gateway` (LDAP upstream unreachable).

---

## 2. Conversation & Multi-Agent API (`server/api/conversation.py`)

Manages chat sessions, message turns, document scoping, user feedback, and token usage analytics.

### `GET /conversations`
Lists all conversations owned by the authenticated user (`common/connectors/postgres/chat.py`).

### `POST /conversations`
Creates a new conversation session with optional initial document attachments and workflow configuration.
- **Request Body**:
  ```json
  {
    "title": "Q3 Gearbox Maintenance Analysis",
    "model": "gpt-4o",
    "document_ids": ["doc_101", "doc_102"],
    "workflow": "focus"
  }
  ```

### `GET /conversations/{chat_id}`
Retrieves full message history, attached documents, persisted agent execution traces, and token usage metadata for a specific chat.

### `POST /conversations/{chat_id}/messages`
Submits a user prompt to `QAManager` (`services/chat/qa_manager.py`).
- **Request Body**:
  ```json
  {
    "content": "Compare the torque specifications across the attached manuals and flag anomalies.",
    "document_ids": ["doc_101", "doc_102"],
    "stream": true
  }
  ```
- **Behavior**:
  1. Runs input through `pii_redactor.py` and `nemo_guardrails.py`.
  2. Triggers multi-agent execution (`ChatAgent` $\rightarrow$ `ResearchAgent` $\rightarrow$ `AnswerAgent`).
  3. Streams incremental tokens and `AgentAction` events over the active WebSocket connection (or returns the full JSON payload if `stream: false`).

### `DELETE /conversations/{chat_id}`
Deletes a conversation and its associated message history.

### `POST /conversations/{chat_id}/messages/{message_id}/feedback`
Submits user thumbs-up/thumbs-down ratings and qualitative comments (`common/connectors/postgres/feedback.py`, wired to `ChatFeedbackDialog.tsx`).
- **Request Body**:
  ```json
  {
    "rating": "positive",
    "comment": "Accurate citations from Section 4.2."
  }
  ```

### `GET /usage`
Returns historical and forecasted token consumption (`client/src/api/usage.ts` & `client/src/lib/tokens/forecast.ts`) backed by `common/connectors/postgres/token.py`.

---

## 3. Document Ingestion & Management API (`server/api/ingest.py`)

Handles file uploads, SharePoint sync triggers, ingestion job status tracking, and corpus management.

### `POST /ingest/upload`
Accepts `multipart/form-data` file uploads (PDF, DOCX, PPTX, XLSX, MD, TXT).
- **Pipeline Trigger**:
  1. Stores raw binary in S3 (`common/connectors/s3/manager.py`).
  2. Dispatches a durable Temporal ingestion workflow (`services/temporal/workflows.py`) or invokes `md_maker` $\rightarrow$ `md_ingestor`.
- **Response (`202 Accepted`)**:
  ```json
  {
    "job_id": "wf-ingest-7f3a91",
    "document_id": "doc_205",
    "status": "PROCESSING"
  }
  ```

### `POST /ingest/sharepoint`
Triggers an incremental or full synchronization of configured SharePoint document libraries (`common/connectors/sharepoint/manager.py`).

### `GET /ingest/documents`
Lists indexed documents accessible to the current user, including chunk counts, language tags, processing status, and S3 download links (`client/src/api/document.ts`).

### `DELETE /ingest/documents/{document_id}`
Removes a document from S3, deletes its vector embeddings, and prunes orphaned nodes/edges from Neo4j.

---

## 4. Real-Time WebSocket Protocol (`SocketProvider.tsx`)

The frontend (`client/src/components/providers/SocketProvider.tsx`) maintains a persistent WebSocket connection to receive low-latency updates during multi-agent execution:

| Event Type | Payload Schema | UI Consumer |
| :--- | :--- | :--- |
| `agent_action` | `{ "agent": "ResearchAgent", "step": "hybrid_rag_search", "status": "running", "detail": "Querying 2 documents..." }` | `AgentActionRow.tsx`, `PersistentTraceBlock.tsx` |
| `tool_call` | `{ "tool": "mcp_ticket_lookup", "args": {...}, "duration_ms": 142 }` | `PersistentTraceBlock.tsx`, `MessageInfoDialog.tsx` |
| `token` | `{ "message_id": "msg_88", "delta": "Based on Section 4.2..." }` | `ChatMessages.tsx`, `styled-markdown.tsx` |
| `citations` | `{ "message_id": "msg_88", "sources": [{ "doc_id": "doc_101", "page": 14, "score": 0.94 }] }` | `ChatDocuments.tsx`, `pdf-viewer.tsx` |
| `example_questions` | `{ "chat_id": "chat_12", "questions": ["What is the max thermal load?", "..."] }` | `ChatTextbox.tsx` |
| `usage_update` | `{ "prompt_tokens": 1240, "completion_tokens": 380, "total_tokens": 1620 }` | `TokenUsageDialog.tsx` |
| `error` | `{ "code": "GUARDRAIL_BLOCKED", "message": "Request violates topical policy." }` | `async-error-alert.tsx` |

---

## 5. Internal Microservice Contracts (`common/microservices/schemas.py`)

Internal service-to-service HTTP calls use standardized Pydantic envelopes (`ServiceRequest` / `ServiceResponse`) carrying:
- `traceparent` / `tracestate` W3C OpenTelemetry context headers.
- `X-User-ID` and `X-User-Roles` propagated from the verified JWT so downstream services (`rag`, `md_ingestor`, `chat`) enforce row- and document-level authorization.