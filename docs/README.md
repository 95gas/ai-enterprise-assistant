# `qa-multiagents-rag` — Technical Documentation Hub

Welcome to the comprehensive engineering documentation for **`qa-multiagents-rag`**, an enterprise-grade, multi-agent Retrieval-Augmented Generation (RAG) and conversational AI platform.

The system combines **Hybrid RAG** (dense vector search + Neo4j Knowledge Graph traversal + cross-encoder reranking), **multi-agent orchestration** with Model Context Protocol (MCP) tools, **durable workflow execution** via Temporal, **multi-modal document ingestion**, **NVIDIA NeMo Guardrails & PII redaction**, and a **white-label React/TypeScript web client** with full OpenTelemetry observability.

---

## Documentation Suite Map

| Document | Scope & Audience |
| :--- | :--- |
| **[System & Microservices Architecture](SYSTEM_ARCHITECTURE.md)** | High-level topology, service boundaries, data persistence (PostgreSQL, Neo4j, S3, SharePoint), inter-service contracts, and end-to-end request flows. |
| **[Multi-Agent Orchestration & Workflows](MULTI_AGENT_AND_WORKFLOWS.md)** | Architecture of `BaseAgent` and the 7 domain agents (`Chat`, `Research`, `Answer`, `Notes`, `Report`, `Ticket`, `UserSupport`), MCP tools, and execution workflows (`Focus`, `ExampleQuestions`). |
| **[Hybrid RAG & Document Ingestion Pipeline](HYBRID_RAG_AND_INGESTION.md)** | Two-stage ingestion (`md_maker` + `md_ingestor`), multi-modal table/image/slide enrichment, `VectorRAG`, `GraphRAG`, metadata filtering, and reranking. |
| **[API Reference & Real-Time Streaming](API_AND_REALTIME_SPEC.md)** | Gateway REST APIs (`/login`, `/conversation`, `/ingest`), internal microservice contracts, WebSocket/Socket event protocol, and trace streaming schemas. |
| **[Security, Privacy & Guardrails](SECURITY_PRIVACY_GUARDRAILS.md)** | Authentication (LDAP + local DB + JWT), NVIDIA NeMo Guardrails integration, automated PII redaction, RBAC document filtering, and secrets management. |
| **[Frontend & White-Label Architecture](FRONTEND_AND_WHITELABEL.md)** | React + Vite + TypeScript client, Shadcn UI components, real-time agent trace visualization, token forecasting, i18n (`en`, `it`, `zh`), and tenant builds (`default`, `carraro`, `mirai`, `necto`). |
| **[Deployment, Observability & Testing](DEPLOYMENT_OBSERVABILITY_TESTING.md)** | Docker Compose stack, DB initialization, Elasticsearch-to-PostgreSQL migration, Temporal workers, OpenTelemetry/Prometheus/Loki/Tempo/Grafana dashboards, and Pytest suite. |

---

## High-Level Technology Stack

| Layer | Technologies & Frameworks |
| :--- | :--- |
| **Frontend Client** | React, TypeScript, Vite, Tailwind CSS, Shadcn/Radix UI, Lingui (`en`, `it`, `zh`), PDF.js, WebSockets |
| **API Gateway & Services** | Python 3.10+, FastAPI, Uvicorn, Pydantic, `uv` dependency management |
| **Multi-Agent & Tooling** | Custom Agent Framework (`BaseAgent`), Model Context Protocol (`mcp_tools.py`), YAML Prompt Registry |
| **Workflow Orchestration** | Temporal (`workflows.py`, `activities.py`, `worker.py`) |
| **Retrieval & Knowledge** | Hybrid Vector Search, Neo4j Knowledge Graph (`GraphRAG`), Cross-Encoder/LLM Reranker |
| **Document Processing** | Multi-format Parsers (PDF, Office, Generic), VLM/LLM Image, Slide & Table Describers, Language Detection |
| **Persistence & Connectors** | PostgreSQL (primary relational & metadata store), Neo4j (graph store), Amazon S3 / Object Storage, Microsoft SharePoint, Elasticsearch (legacy migration support) |
| **Safety & Governance** | NVIDIA NeMo Guardrails, Automated PII Redactor, LDAP / JWT Auth |
| **Observability & Ops** | Docker & Docker Compose, Nginx, OpenTelemetry Collector, Prometheus, Loki, Tempo, Grafana |

---

## Repository Directory Blueprint

```text
qa-multiagents-rag/
├── client/                     # React + TypeScript + Vite SPA frontend
│   ├── config/                 # Multi-tenant white-label overrides (carraro, default, mirai, necto)
│   ├── public/                 # Static assets (logo.svg, icon.svg)
│   └── src/
│       ├── api/                # Typed HTTP clients (apps, chat, document, featureFlags, model, usage)
│       ├── components/         # Providers, chat/agent trace sections, and Shadcn/custom UI primitives
│       ├── docs/               # Localized in-app user manuals, privacy policies, and changelogs
│       ├── lib/                # Hooks, token usage forecasting, TypeScript domain types
│       ├── locales/            # Lingui translation catalogs (en, it, zh)
│       └── routes/             # Application pages (ask, chats, documents, login, settings, pages)
├── docker/                     # Container definitions & observability stack
│   ├── docker-compose.yml      # Full multi-container orchestration
│   ├── observability/          # OpenTelemetry, Prometheus, Loki, Tempo, and Grafana provisioning/dashboards
│   └── {chat,client,rag,server,services}/  # Service-specific Dockerfiles & DB bootstrap scripts
├── docs/                       # Architectural & operational Markdown documentation
└── server/                     # Python 3.10+ backend monorepo
    ├── api/                    # Public Gateway FastAPI routers (conversation, ingest, login)
    ├── config/                 # YAML service configs, prompts, guardrails, and secrets templates
    ├── scripts/                # Admin & migration utilities (create_user, ES-to-Postgres migration)
    ├── src/
    │   ├── common/             # Shared connectors, LLM/Model managers, guardrails, telemetry, schemas
    │   ├── knowledge/          # Vector and Graph knowledge abstractions
    │   ├── schema/             # Core domain Pydantic schemas (knowledge_graph, user)
    │   ├── services/           # Independent microservices (authentication, chat, md_ingestor, md_maker, rag, temporal)
    │   ├── user/               # User domain management
    │   └── utils/              # Environment and bootstrap helpers
    └── tests/                  # Automated Pytest unit and integration test suite
```

---

## Quick Start (Local Development)

1. **Configure Environment & Secrets**:
   - Copy `server/config/secrets.env.example` to `server/config/secrets.env` and set database credentials, LLM API keys, JWT secrets, and connector tokens. The same file is used by Docker Compose and local PowerShell-launched services.
2. **Start Infrastructure & Microservices**:
   - Launch backing infrastructure (PostgreSQL, Neo4j, S3/MinIO, Temporal, Observability stack) via `docker/docker-compose.yml`.
   - On Windows environments, use `start-dev.ps1` to bootstrap local development services, or start individual FastAPI services using `uv run`.
3. **Initialize Database & Admin User**:
   - Run `docker/server/DB_initialization.py` to create relational tables.
   - Run `python server/scripts/create_user.py` to provision initial user accounts.
4. **Launch Frontend**:
   - Navigate to `client/`, install dependencies (`yarn install`), and run the dev server (`yarn dev`).