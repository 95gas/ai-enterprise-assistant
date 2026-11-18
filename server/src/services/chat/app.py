"""
Chat Microservice — Standalone FastAPI application.

Handles:
  • Authentication (login / logout / session check)
  • Chat CRUD (create, list, retrieve, update, delete)
  • Chat invocation (streaming answers through the agent pipeline)
  • User token limits
  • Feedback ingestion
  • WebSocket (SocketIO) support for real-time streaming

This service is a thin HTTP layer on top of the existing core modules:
  src.services.chat  – ChatManager, QAManager, agents, workflows
  src.services.rag           – VectorRAG, GraphRAG, CustomRetriever
  src.services.authentication     – AuthService, JWT
"""

import os
import sys
import asyncio
import logging
import traceback
import uuid
import warnings
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, date, timezone, timedelta
from typing import Any, Dict, List, Optional, Literal, Union

import httpx
import jsonpickle
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------------
from src.common.logging.logger import DebugLogger
from src.common.privacy.pii_redactor import get_default_redactor, redact_nested
from src.common.privacy.nemo_guardrails import NemoGuardrailsService, GuardrailViolation
from src.common.telemetry import configure_fastapi_metrics
from src.common.models.manager import ModelManager
from src.common.models.llama_config import LIConfig
from src.common.connectors.postgres.chat import ChatRepo
from src.common.connectors.postgres.feedback import FeedbackRepo
from src.common.connectors.postgres.token import TokenRepo
from src.common.connectors.postgres.user import UserRepo
from src.services.rag.orchestrator import get_main_agent
from src.services.chat.schema import AgentProgress, Response
from src.services.authentication.client import require_user
from config.settings import settings

from llama_index.core.base.llms.types import ChatMessage

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
ORIGINS = settings.system.allowed_origins
PORT = int(os.getenv("CHAT_SERVICE_PORT", "8001"))
MODELS_INFO_DICT = settings.models_info.model_dump()
DATE_FORMAT = settings.DATE_FORMAT

logger = DebugLogger(user="undefined", class_name="chat-service", main_feature="SYSTEM")

# ---------------------------------------------------------------------------
# Shared singletons (populated during lifespan)
# ---------------------------------------------------------------------------
main_agent = None
pii_redactor = None
nemo_guardrails = None
# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str


class ChatCreateRequest(BaseModel):
    chat_name: Optional[str] = None


class ChatSaveRequest(BaseModel):
    conversation: List[Dict[str, Any]]
    chat_name: Optional[str] = None


class FeedbackRequest(BaseModel):
    feedback: Dict[str, Any]


class ChatInvokeRequest(BaseModel):
    invoke: Literal["regenerate", "expand", "chat"]
    selected_language: Literal["en", "it", "zh"] = "en"
    provider: Literal["azure", "openai", "openrouter", "google", "ollama", "huggingface"]
    llm_model: str
    workflow: Literal[
        "ExampleQuestions", "FocusMode", "UserSupport", "QA",
        "Report", "AllForOne", "General", "DeepResearch",
    ]
    user_question: str
    doc_search: bool = True
    web_search: bool = False
    internal_knowledge: bool = False
    checkpoint: Optional[int] = None
    selected_documents: List[Dict[str, Any]] = []
    selected_page_numbers: List[Dict[str, Any]] = []
    selected_chunk_numbers: List[Dict[str, Any]] = []
    assistant_answer: Optional[Dict] = None
    chat_name: Optional[str] = None
    socket_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_agent, pii_redactor, nemo_guardrails
    logger.info("Chat Service starting – initializing core components...")
    LIConfig()
    main_agent = get_main_agent()
    pii_redactor = get_default_redactor()
    nemo_guardrails = NemoGuardrailsService()
    logger.success("Chat Service ready.")
    yield
    logger.info("Chat Service shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Chat Microservice",
    description="Handles authentication, chat management, and LLM invocations.",
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
configure_fastapi_metrics(app, "chat-service")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/healthcheck")
async def healthcheck():
    return {"healthcheck": "CHAT SERVICE OK"}


@app.get("/")
async def root():
    return {"service": "chat-microservice", "status": "running"}


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------
@app.post("/login")
async def login(body: LoginRequest):
    auth_service_url = os.getenv("AUTH_SERVICE_URL", "http://localhost:8003")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{auth_service_url.rstrip('/')}/login",
                json=body.model_dump(),
            )
        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        response.raise_for_status()
        return response.json()
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        logger.error(f"Authentication service request failed: {exc}")
        raise HTTPException(status_code=503, detail="Authentication service unavailable.") from exc


@app.get("/login")
async def get_logged_in(user=Depends(require_user)):
    return user.to_json()


@app.post("/logout")
async def logout(user=Depends(require_user)):
    logger.info(f"User {user.email} logged out.")
    return JSONResponse(status_code=204, content=None)


# ---------------------------------------------------------------------------
# User tokens
# ---------------------------------------------------------------------------
@app.get("/general/v0/user_token")
async def get_user_tokens(user=Depends(require_user)):
    try:
        db_manager = main_agent.get_postgres_connection()
        token_manager = TokenRepo(db_manager=db_manager)
        limit_info_models = token_manager.get_limits_info_per_model(
            user_email=user.email, models_info_dict=MODELS_INFO_DICT
        )
        tokens_usage_dict = token_manager.get_overall_tokens_usage_per_model(
            user_email=user.email, limit_info_models=limit_info_models
        )
        grouped = []
        for model_info in MODELS_INFO_DICT["chat_models"]:
            custom_name = model_info["custom_name"]
            provider = model_info["provider"]
            actual_model = MODELS_INFO_DICT["providers"][provider][custom_name]["actual_model_name"]
            token_manager.check_and_update_resetting_datetime(
                model_name=actual_model, limit_info_models=limit_info_models
            )
            limit_info_models[actual_model][provider].update(
                tokens_usage_dict.get(actual_model, {}).get(provider, {})
            )
            limit_info_models[actual_model][provider].update(
                MODELS_INFO_DICT["providers"][provider][custom_name]
            )
            grouped.append({custom_name: {provider: limit_info_models[actual_model][provider]}})
        return grouped
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get token info: {e}")


# ---------------------------------------------------------------------------
# Chat CRUD
# ---------------------------------------------------------------------------
@app.get("/general/v0/chats")
async def list_chats(user=Depends(require_user)):
    try:
        db_manager = main_agent.get_postgres_connection()
        chat_repo = ChatRepo(db_manager=db_manager)
        conversations = chat_repo.get_all(user_email=user.email)
        chats = [{"name": c["_source"]["chat_name"], "id": c["_id"]} for c in conversations]
        return chats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/general/v0/chats")
async def create_chat(body: ChatCreateRequest, user=Depends(require_user)):
    try:
        db_manager = main_agent.get_postgres_connection()
        chat_repo = ChatRepo(db_manager=db_manager)
        payload = {
            "user": user.email,
            "chat_name": body.chat_name,
            "conversation": [],
            "last_edit": datetime.now(timezone.utc).strftime(DATE_FORMAT),
            "creation_date": datetime.now(timezone.utc).strftime(DATE_FORMAT),
        }
        resp = chat_repo.add(payload)
        if resp.get("result") == "created":
            return {"id": resp["_id"], "name": body.chat_name}
        raise HTTPException(status_code=500, detail="Failed to create chat.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/general/v0/chats/{chat_id}")
async def get_chat(chat_id: str, user=Depends(require_user)):
    try:
        db_manager = main_agent.get_postgres_connection()
        chat_repo = ChatRepo(db_manager=db_manager)
        return chat_repo.get(user_email=user.email, chat_id=chat_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/general/v0/chats/{chat_id}")
async def save_chat(chat_id: str, body: ChatSaveRequest, user=Depends(require_user)):
    try:
        db_manager = main_agent.get_postgres_connection()
        chat_repo = ChatRepo(db_manager=db_manager)
        payload = {
            "conversation": body.conversation,
            "last_edit": datetime.now(timezone.utc).strftime(DATE_FORMAT),
        }
        if body.chat_name:
            payload["chat_name"] = body.chat_name
        resp = chat_repo.save(chat_id, payload)
        return resp
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/general/v0/chats/{chat_id}")
async def delete_chat(chat_id: str, user=Depends(require_user)):
    try:
        db_manager = main_agent.get_postgres_connection()
        chat_repo = ChatRepo(db_manager=db_manager)
        resp = chat_repo.delete(user.email, chat_id)
        return resp
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
@app.post("/general/v0/chats/{chat_id}/feedback")
async def submit_feedback(chat_id: str, body: FeedbackRequest, user=Depends(require_user)):
    try:
        db_manager = main_agent.get_postgres_connection()
        feedback_repo = FeedbackRepo(db_manager=db_manager)
        feedback = body.feedback
        feedback["user_email"] = user.email
        feedback["timestamp"] = datetime.now(timezone.utc).strftime(DATE_FORMAT)
        return feedback_repo.save(chat_id, feedback)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Chat Invocation (main endpoint)
# ---------------------------------------------------------------------------
@app.post("/general/v0/chats/{chat_id}/invoke")
async def invoke_chat(chat_id: str, body: ChatInvokeRequest, user=Depends(require_user)):
    """Invoke the LLM agent pipeline and return the final response."""
    try:
        if not body.user_question:
            raise HTTPException(status_code=400, detail="'user_question' is required.")

        # PII redaction
        body.user_question = pii_redactor.redact(body.user_question)

        # Guardrails input check
        body.user_question = await nemo_guardrails.check_input(body.user_question)

        if body.assistant_answer:
            body.assistant_answer = redact_nested(body.assistant_answer, pii_redactor)

        # Validate user access
        agent = main_agent
        agent.user = user.email
        db_manager = agent.get_postgres_connection()
        user_repo = UserRepo(db_manager=db_manager)
        token_manager = TokenRepo(db_manager=db_manager)

        _validate_user_access(user, body.llm_model, body.provider, user_repo, token_manager)

        # Get LLM
        model_manager = ModelManager()
        model_manager.config_log(user.email)
        llm = model_manager.get_model({"custom_name": body.llm_model, "provider": body.provider})

        # Prepare chat context
        chat_manager = agent.get_new_chat_manager()
        chat_repo = ChatRepo(db_manager=db_manager)
        user_message = chat_manager.chat_history_manager._create_user_message(
            user_query=body.user_question,
            selected_docs=body.selected_documents,
        )
        conversation = chat_repo.get(user_email=user.email, chat_id=chat_id)
        conversation = redact_nested(conversation, pii_redactor)

        # Chat history
        messages = conversation.get("messages", [])
        if body.checkpoint:
            messages = messages[:body.checkpoint]
        chat_manager.initialize_chat(chat_history=messages)
        chat_history = chat_manager.get_chat_history()
        chat_history.append(user_message)
        chat_manager.chat_history_manager.set_history(chat_history)

        # Recorded notes
        recorded_notes = {
            k: v
            for m in messages if m.get("recorded_notes")
            for k, v in m["recorded_notes"].items()
        }

        # Workflow override (backward compat)
        workflow = body.workflow
        if str(body.user_question).startswith("!"):
            workflow = "AllForOne"
        elif str(body.user_question).startswith("?"):
            workflow = "ExampleQuestions"

        req_info = {
            "chat_id": chat_id,
            "workflow": workflow,
            "chat_history": chat_history,
            "provider": body.provider,
            "user_roles": user.groups,
            "doc_search": body.doc_search,
            "web_search": body.web_search,
            "internal_knowledge": body.internal_knowledge,
            "selected_language": body.selected_language,
            "selected_documents": body.selected_documents,
            "selected_page_numbers": body.selected_page_numbers,
            "selected_chunk_numbers": body.selected_chunk_numbers,
            "prev_answer": ChatMessage(
                role="assistant",
                content=body.assistant_answer["content"],
                additional_kwargs={"sources": body.assistant_answer["sources"]},
            ) if body.assistant_answer else None,
            "generate_chat_name": not body.chat_name,
            "provided_sources": [],
            "report_type": "free",
            "recorded_notes": recorded_notes,
        }

        # Generate answer
        response_generator = chat_manager.get_answer(llm=llm, req_info=req_info)
        final_response = None
        action_frames = []

        async for response in response_generator:
            if isinstance(response, str):
                continue
            final_resp, status_code = response
            if isinstance(final_resp, AgentProgress):
                frame = {
                    "phase": final_resp.phase,
                    "id": final_resp.id,
                    "tool_name": final_resp.tool_name,
                    "label": final_resp.label,
                    "message": pii_redactor.redact(final_resp.message),
                    "language": final_resp.language,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": final_resp.duration_ms,
                }
                action_frames.append(frame)
                continue

            final_resp = redact_nested(final_resp, pii_redactor)
            if isinstance(final_resp, dict) and isinstance(final_resp.get("answer"), str):
                final_resp["answer"] = await nemo_guardrails.check_output(
                    body.user_question, final_resp["answer"]
                )
                final_resp["answer"] = pii_redactor.redact(final_resp["answer"])
            if isinstance(final_resp, dict) and action_frames:
                metadata = final_resp.get("metadata") or {}
                metadata["actions"] = action_frames
                final_resp["metadata"] = metadata
            final_response = final_resp

        if final_response is None:
            raise HTTPException(status_code=500, detail="Stream ended without a final response.")

        return final_response

    except GuardrailViolation:
        raise HTTPException(status_code=403, detail="Blocked by content safety policy.")
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat invocation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error.")


def _validate_user_access(
    current_user, selected_model_name: str, selected_provider: str,
    user_repo: UserRepo, token_manager: TokenRepo,
):
    """Check trial status and token limits."""
    user_info = user_repo.get(current_user.id)
    actual_model = MODELS_INFO_DICT["providers"][selected_provider][selected_model_name]["actual_model_name"]

    expiration_date = datetime.strptime(user_info.expiring_date_trial, DATE_FORMAT).date()
    if expiration_date < date.today():
        raise PermissionError("Your trial period has expired!")

    limit_info = token_manager.get_limits_info_per_model(
        user_email=current_user.email, models_info_dict=MODELS_INFO_DICT
    )
    token_manager.check_and_update_resetting_datetime(
        model_name=actual_model, limit_info_models=limit_info
    )
    token_usage = token_manager.get_overall_tokens_usage_per_model(
        user_email=current_user.email, limit_info_models=limit_info
    )
    total_usage = sum(
        data.get("tot_tokens_timeframe", 0)
        for model_data in token_usage.values()
        for data in model_data.values()
    )
    if total_usage >= user_info.tot_token_limit:
        raise PermissionError("Overall tokens limit reached!")

    tf_tokens = token_usage.get(actual_model, {}).get(selected_provider, {}).get("tot_tokens_timeframe", 0)
    limit = limit_info.get(actual_model, {}).get(selected_provider, {}).get("tokens_limit", 0)
    if tf_tokens >= limit:
        raise PermissionError(f"Tokens limit reached for model {selected_model_name}!")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.services.chat.app:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="info",
    )
