"""
RAG Microservice — Standalone FastAPI application.

Handles:
  • Document ingestion (upload, extraction, chunking, embedding, indexing)
  • Document retrieval and listing
  • Document deletion
  • Knowledge base management (vector + graph)
  • Markdown page retrieval
  • Bucket listing
  • Integration with Temporal for orchestrated pipelines

This service wraps the existing core modules:
  src.services.rag            – VectorRAG, GraphRAG, orchestrator
  src.core.knowledge      – VectorManager, GraphManager
  src.services.temporal   – Temporal document workflows
  src.common.connectors   – Neo4j, S3, Postgres
"""

import os
import json
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, Depends
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.encoders import jsonable_encoder

# ---------------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------------
from src.common.logging.logger import DebugLogger
from src.common.models.llama_config import LIConfig
from src.common.utils.validator import FileManager
from src.common.schema.documents import DocumentToProcess, ProcessingConfig
from src.services.authentication.client import require_user
from src.services.rag.orchestrator import get_main_agent
from src.services.rag.retriever import CustomRetriever
from src.services.chat.temporal import temporal_enabled
from src.services.temporal.client import TemporalMicroserviceClient
from src.common.telemetry import configure_fastapi_metrics
from config.settings import settings

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
ORIGINS = settings.system.allowed_origins
PORT = int(os.getenv("RAG_SERVICE_PORT", "8002"))
DATE_FORMAT = settings.DATE_FORMAT
STORAGE_PATH = settings.STORAGE_PATH
MAX_PRIVATE_DOCS_PER_USER = settings.MAX_PRIVATE_DOCS_PER_USER

FAST_SUPPORTED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}

logger = DebugLogger(user="undefined", class_name="rag-service", main_feature="SYSTEM")
file_manager = FileManager()

# ---------------------------------------------------------------------------
# Shared singletons (populated during lifespan)
# ---------------------------------------------------------------------------
main_agent = None
temporal_client = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sanitize_name(name: str) -> str:
    """Sanitizes filename while preserving the extension."""
    import re
    base_name, ext = os.path.splitext(name)
    safe_base = re.sub(r"[^a-zA-Z0-9-]", "_", base_name)
    return safe_base + ext


def convert_paths(obj):
    if isinstance(obj, dict):
        return {k: convert_paths(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_paths(i) for i in obj]
    elif isinstance(obj, Path):
        return str(obj)
    return obj


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_agent, temporal_client
    logger.info("RAG Service starting – initializing core components...")
    LIConfig()
    main_agent = get_main_agent()
    temporal_client = TemporalMicroserviceClient()
    logger.success("RAG Service ready.")
    yield
    logger.info("RAG Service shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="RAG Microservice",
    description="Handles document ingestion, retrieval, deletion, and knowledge management.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
configure_fastapi_metrics(app, "rag-service")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/healthcheck")
async def healthcheck():
    return {"healthcheck": "RAG SERVICE OK"}


@app.get("/")
async def root():
    return {
        "service": "rag-microservice",
        "status": "running",
        "temporal_enabled": temporal_enabled(),
    }


# ---------------------------------------------------------------------------
# Document listing
# ---------------------------------------------------------------------------
@app.get("/general/v0/docs")
async def list_documents(user=Depends(require_user)):
    """Retrieve all document records accessible by the user."""
    try:
        db_manager_neo4j = main_agent.get_neo4j_connection()
        db_manager_neo4j.config_log(user.email)
        visibility_groups = user.groups
        documents = db_manager_neo4j.retrieve_documents(visibility_groups=visibility_groups)
        return documents
    except Exception as e:
        logger.error(f"Error retrieving docs: {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve document records.")


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8192)
    top_k: int = Field(default=10, ge=1, le=100)
    selected_documents: List[str] = Field(default_factory=list)
    selected_page_numbers: List[int] = Field(default_factory=list)
    selected_chunk_numbers: List[int] = Field(default_factory=list)


@app.post("/general/v0/retrieve")
async def retrieve_documents(
    body: RetrieveRequest,
    user=Depends(require_user),
):
    """Search the knowledge base, restricted to the authenticated user's groups."""
    try:
        retriever = CustomRetriever(
            database_manager=main_agent.get_neo4j_connection(),
            graph_store=main_agent.graph_rag.get_graph_store(),
            similarity_top_k=body.top_k,
            user=user.email,
        )
        retriever.set_groups(user.groups or [])
        if body.selected_documents:
            retriever.set_selected_documents(body.selected_documents)
        if body.selected_page_numbers:
            retriever.set_selected_page_numbers(body.selected_page_numbers)
        if body.selected_chunk_numbers:
            retriever.set_selected_chunk_numbers(body.selected_chunk_numbers)

        nodes = await asyncio.to_thread(retriever.retrieve, body.query)
        return {
            "results": [
                {
                    "text": node.node.get_content(),
                    "score": node.score,
                    "metadata": jsonable_encoder(node.node.metadata),
                }
                for node in nodes
            ]
        }
    except Exception as e:
        logger.error(f"Error retrieving documents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not retrieve documents.")


def _require_upload_permission(user, s3_bucket: str) -> None:
    allowed = (
        user.permissions.upload_private
        if s3_bucket == "users"
        else user.permissions.upload_common
    )
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail="This action requires document upload privileges.",
        )


# ---------------------------------------------------------------------------
# Document pages
# ---------------------------------------------------------------------------
@app.get("/general/v0/docs/{s3_bucket}/{s3_path:path}/{filename}")
async def get_document_pages(
    s3_bucket: str,
    s3_path: str,
    filename: str,
    s3_page: Optional[str] = None,
    user=Depends(require_user),
):
    """Retrieve markdown pages for a specific document."""
    try:
        s3_manager = main_agent.get_s3_connection()
        s3_manager.config_log(user.email)

        if s3_page is None:
            pages = s3_manager.get_markdowns(
                s3_bucket=s3_bucket, s3_path=s3_path, filename=filename
            )
            pages_refs = {}
            for page_s3_path in pages:
                page_name = page_s3_path.key.split("_page")[-1].replace(".md", "")
                pages_refs[page_name] = page_s3_path.key.split("/markdown/")[-1]
            return pages_refs
        else:
            page_binary = s3_manager.get_markdown_page(
                s3_bucket=s3_bucket, s3_path=s3_path,
                filename=filename, s3_page=s3_page,
            )
            return PlainTextResponse(
                content=page_binary.decode("utf-8"),
                media_type="text/markdown",
            )
    except Exception as e:
        logger.error(f"Error retrieving pages: {e}")
        raise HTTPException(status_code=404, detail="Pages not found.")


# ---------------------------------------------------------------------------
# Document deletion
# ---------------------------------------------------------------------------
@app.delete("/general/v0/docs/{s3_bucket}/{s3_path:path}/{filename}")
async def delete_document(
    s3_bucket: str, s3_path: str, filename: str,
    user=Depends(require_user),
):
    """Delete a file from storage and its associated data from Neo4j."""
    try:
        _require_upload_permission(user, s3_bucket)
        if "/markdown/" in s3_path:
            raise HTTPException(status_code=400, detail="s3_path cannot contain '/markdown/'.")

        s3_manager = main_agent.get_s3_connection()
        s3_manager.config_log(user.email)
        db_manager_neo4j = main_agent.get_neo4j_connection()
        db_manager_neo4j.config_log(user.email)

        # Delete from storage
        try:
            s3_manager.delete_markdowns(s3_bucket=s3_bucket, s3_path=s3_path, filename=filename)
        except FileNotFoundError:
            logger.warning(f"File not found in S3, may already be deleted.")

        # Delete from database
        db_manager_neo4j.delete_document(s3_bucket=s3_bucket, s3_path=s3_path, filename=filename)
        return {"message": f"Successfully deleted '{s3_path}/{filename}'."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail="Error deleting file.")


# ---------------------------------------------------------------------------
# Buckets
# ---------------------------------------------------------------------------
@app.get("/general/v0/docs/buckets")
async def get_buckets(user=Depends(require_user)):
    """Retrieve all available S3 buckets."""
    try:
        s3_manager = main_agent.get_s3_connection()
        s3_manager.config_log(user.email)
        return s3_manager.get_folders()
    except Exception as e:
        logger.error(f"Error retrieving buckets: {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve buckets.")


# ---------------------------------------------------------------------------
# Document processing / ingestion
# ---------------------------------------------------------------------------
class ProcessRequest(BaseModel):
    docs_to_process: str  # JSON-encoded list


@app.post("/general/v0/docs/process")
async def process_files(request: Request, user=Depends(require_user)):
    """
    Upload and process documents through the extraction → ingestion pipeline.

    Accepts multipart/form-data with file_0, file_1, ... and metadata fields.
    """
    try:
        form = await request.form()
        if not any(k.startswith("file_") for k in form):
            raise HTTPException(status_code=400, detail="No files provided.")

        main_agent.initialize(user=user.email)
        db_manager_neo4j = main_agent.get_neo4j_connection()
        s3_manager = main_agent.get_s3_connection()

        # Parse files
        docs_to_process = []
        docs_not_processed = {}
        i = 0
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            while f"file_{i}" in form:
                upload_file = form[f"file_{i}"]
                filename = sanitize_name(upload_file.filename)
                s3_bucket = form.get(f"s3_bucket_{i}", "shared")
                s3_path = form.get(f"s3_path_{i}", "Common")
                method = form.get(f"method_{i}", "full")

                _require_upload_permission(user, s3_bucket)
                if s3_bucket == "users":
                    s3_path = "Private"

                # Check duplicates
                if db_manager_neo4j.check_duplicate_doc(
                    s3_bucket=s3_bucket, s3_path=s3_path, filename=filename
                ):
                    docs_not_processed[upload_file.filename] = "File already stored."
                    i += 1
                    continue

                # Check extension
                if not file_manager.allowed_file(filename):
                    docs_not_processed[upload_file.filename] = "File type not allowed."
                    i += 1
                    continue

                # Write temp file
                file_content = await upload_file.read()
                tmp_file = tmp_path / filename
                with open(tmp_file, "wb") as f:
                    f.write(file_content)

                visibility_groups_str = form.get(f"visibility_groups_{i}", "")
                visibility_groups = (
                    [g.strip() for g in visibility_groups_str.split(",") if g.strip()]
                    if s3_bucket != "users"
                    else [user.email]
                )

                docs_to_process.append(DocumentToProcess(
                    filename=filename,
                    visibility_groups=visibility_groups,
                    processing=ProcessingConfig(method=method, tables=True, images=True),
                    content_type=upload_file.content_type,
                    s3_bucket=s3_bucket,
                    s3_path=s3_path,
                    uploaded_by=user.email,
                    og_last_modified=datetime.now(timezone.utc).strftime(DATE_FORMAT),
                    og_filename=upload_file.filename,
                    og_uri=None,
                    source_filepath=tmp_file,
                ))
                i += 1

            unsupported_fast_docs = {
                doc.og_filename
                for doc in docs_to_process
                if doc.processing.method == "fast"
                and doc.content_type not in FAST_SUPPORTED_MIMES
            }
            if unsupported_fast_docs:
                raise HTTPException(
                    status_code=400,
                    detail="Fast extraction does not support: "
                    + ", ".join(sorted(unsupported_fast_docs)),
                )

            if docs_not_processed and not docs_to_process:
                return JSONResponse(
                    status_code=400,
                    content={"message": "No files could be processed.", "data": docs_not_processed},
                )

            if not temporal_enabled() or temporal_client is None:
                raise HTTPException(
                    status_code=503,
                    detail="Temporal ingestion is unavailable. Enable Temporal and start its worker.",
                )

            serialized = [convert_paths(d.model_dump()) for d in docs_to_process]
            result = await temporal_client.execute_document_ingestion(
                docs_to_process=serialized,
                user=user.email,
            )
            result["skipped"] = docs_not_processed
            return {"message": "Files processed via Temporal.", "data": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Orchestrated ingestion (Temporal endpoint)
# ---------------------------------------------------------------------------
@app.post("/orchestrate_ingestion")
async def orchestrate_ingestion(
    request: Request,
    user=Depends(require_user),
):
    """Trigger full end-to-end ingestion pipeline via Temporal."""
    try:
        form = await request.form()
        docs_str = form.get("docs_to_process")
        mode = form.get("mode", "full")

        if not docs_str:
            raise HTTPException(status_code=400, detail="Missing 'docs_to_process'.")

        docs = json.loads(docs_str)
        user_email = user.email
        for doc in docs:
            _require_upload_permission(user, doc.get("s3_bucket", "shared"))

        if temporal_enabled() and temporal_client:
            result = await temporal_client.execute_document_ingestion(
                docs_to_process=docs, user=user_email, mode=mode,
            )
            return {"status": "success", "data": result, "orchestrator": "temporal"}
        else:
            raise HTTPException(
                status_code=503,
                detail="Temporal ingestion is unavailable. Enable Temporal and start its worker.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Orchestration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.services.rag.app:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="info",
    )
