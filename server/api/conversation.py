from functools import wraps
from json import JSONEncoder
import asyncio, traceback, jsonpickle
from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import List, Dict, Any, Optional, Literal

import flask_login
from flask_socketio import emit
from flask import Blueprint, request, jsonify, current_app, g, has_app_context

from llama_index.core.base.llms.types import ChatMessage

from src.common.connectors.postgres.feedback import FeedbackRepo
from src.common.connectors.postgres.token import TokenRepo
from src.common.connectors.postgres.chat import ChatRepo
from src.common.connectors.postgres.user import UserRepo
from src.common.models.manager import ModelManager
from src.services.chat.schema import AgentProgress
from src.common.logging.logger import DebugLogger
from src.common.privacy.pii_redactor import redact_nested
from src.common.privacy.nemo_guardrails import GuardrailViolation
from src.common.telemetry import trace_chat_turn
from config.settings import settings
from src.schema.user import User

MODELS_INFO_DICT = settings.models_info.model_dump()
DATE_FORMAT = settings.DATE_FORMAT


class ResponseEncoder(JSONEncoder):
    def default(self, o):
        return o.__dict__


@dataclass
class ChatInteractionRequest:
    """Represents the data for a chat interaction request."""
    invoke: Literal["regenerate", "expand", "chat"]
    selected_language: Literal["en", "it", "zh"]
    provider: Literal["azure", "openai", "openrouter", "google", "ollama", "huggingface"]
    llm_model: str
    workflow: Literal[
        "ExampleQuestions",
        "FocusMode",
        "UserSupport",
        "QA",
        "Report",
        "AllForOne",
        "General",
        "DeepResearch",
    ]
    user_question: str
    doc_search: bool
    web_search: bool
    internal_knowledge: bool
    checkpoint: Optional[int] = None
    selected_documents: List[Dict[str, Any]] = field(default_factory=list)
    selected_page_numbers: List[Dict[str, Any]] = field(default_factory=list)
    selected_chunk_numbers: List[Dict[str, Any]] = field(default_factory=list)
    assistant_answer: Optional[Dict] = None
    chat_name: Optional[str] = None
    socket_id: Optional[str] = None


chat_router = Blueprint("chat_router", __name__)

# --- Safe Globals ---
# These do not depend on `current_app` and can be initialized on import.
response_encoder = ResponseEncoder()
logger = DebugLogger()


# --- Service Loader ---
# This hook runs before *every* request handled by this blueprint.
# It safely initializes all services using `current_app` and stores them
# in `g`, which is a per-request global context.
@chat_router.before_request
def load_services():
    """Load services into the Flask request global `g`."""
    if not hasattr(g, 'main_agent'):
        g.main_agent = current_app.main_agent
        g.db_manager = g.main_agent.get_postgres_connection()
        g.user_repo = UserRepo(db_manager=g.db_manager)
        g.chat_manager = ChatRepo(db_manager=g.db_manager)
        g.feedback_manager = FeedbackRepo(db_manager=g.db_manager)
        g.token_manager = TokenRepo(db_manager=g.db_manager)


# --- Decorator ---
def setup_route(func):
    """
    A decorator to handle common setup tasks for routes,
    including user identification, logging configuration, and API request logging.
    It now pulls services from the request global `g`.
    """

    @wraps(func)
    @flask_login.login_required
    def decorated_function(*args, **kwargs):
        # `g` is populated by the `before_request` hook before this runs
        user_email = flask_login.current_user.email
        g.chat_manager.logger.set_user(user_email)
        g.user_repo.logger.set_user(user_email)
        g.feedback_manager.logger.set_user(user_email)
        g.token_manager.logger.set_user(user_email)
        logger.set_user(user_email)  # This is the safe global logger
        logger.set_class_name("conversation")
        logger.set_main_feature("CHAT")
        g.db_manager.config_log(user_email)
        logger.api(f"{request.method} {request.path}")
        # Pass the user object to the route function
        return func(flask_login.current_user, *args, **kwargs)

    return decorated_function


def create_error_response(message, status_code=500, log_exception=False):
    """Creates a consistent JSON error response and logs the error."""
    if has_app_context():
        redactor = current_app.extensions.get("pii_redactor")
        if redactor is not None:
            message = redactor.redact(message)
    logger.error(f"Error: {message}")
    if log_exception:
        logger.debug(traceback.format_exc())
    return jsonify({"error": {"message": message}}), status_code


async def handle_streaming_response(
    response_generator,
    chat_id,
    socket_id,
    redactor,
    guardrails,
    workflow: str,
    user_input: str,
):
    """Guard the completed response before emitting any generated text."""
    action_frames = []
    async for response in response_generator:
        if isinstance(response, str):
            continue
        else:
            final_resp, status_code = response
            if isinstance(final_resp, AgentProgress):
                frame = {
                    "type": "agent-action",
                    "phase": final_resp.phase,
                    "id": final_resp.id,
                    "tool_name": final_resp.tool_name,
                    "label": final_resp.label,
                    "message": redactor.redact(final_resp.message),
                    "detail": None,
                    "language": final_resp.language,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "tokens_in": None,
                    "tokens_out": None,
                    "duration_ms": final_resp.duration_ms,
                    "meta": {},
                }
                action_frames.append({key: value for key, value in frame.items() if key != "type"})
                if socket_id:
                    emit(f"chat-{chat_id}", frame, namespace="/", to=socket_id)
                continue
            final_resp = redact_nested(final_resp, redactor)
            if isinstance(final_resp, dict) and isinstance(final_resp.get("answer"), str):
                final_resp["answer"] = await guardrails.check_output(
                    user_input,
                    final_resp["answer"],
                )
                final_resp["answer"] = redactor.redact(final_resp["answer"])
            if isinstance(final_resp, dict) and action_frames:
                metadata = final_resp.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                metadata["actions"] = action_frames
                final_resp["metadata"] = metadata
            telemetry = current_app.extensions.get("telemetry")
            metadata = final_resp.get("metadata") if isinstance(final_resp, dict) else None
            if telemetry and isinstance(metadata, dict):
                telemetry.record_tokens(
                    input_tokens=int(metadata.get("input_tokens", 0)),
                    output_tokens=int(metadata.get("output_tokens", 0)),
                    workflow=workflow,
                )
            answer = final_resp.get("answer") if isinstance(final_resp, dict) else None
            if socket_id and isinstance(answer, str):
                for start in range(0, len(answer), 256):
                    emit(
                        f"chat-{chat_id}",
                        answer[start:start + 256],
                        namespace="/",
                        to=socket_id,
                    )
            logger.success(f"Request for chat {chat_id} completed successfully.")
            return response_encoder.encode(final_resp), status_code
    return create_error_response("Stream ended without a final response.", 500)


# --- Routes ---
# All routes now use `g.service_name` instead of the old global variables.

@chat_router.route("/general/v0/user_token", methods=["GET"])
@setup_route
def get_user_tokens(current_user):
    """Endpoint to get the token for the current user."""
    try:
        logger.info(f"Getting info tokens for user {current_user.id}.")
        limit_info_models = g.token_manager.get_limits_info_per_model(user_email=current_user.email,
                                                                         models_info_dict=MODELS_INFO_DICT)

        tokens_usage_dict = g.token_manager.get_overall_tokens_usage_per_model(user_email=current_user.email,
                                                                                  limit_info_models=limit_info_models)
        grouped_tokens_info = list()
        for model_info in MODELS_INFO_DICT["chat_models"]:
            custom_name = model_info["custom_name"]
            provider = model_info["provider"]
            actual_model_name = MODELS_INFO_DICT["providers"][provider][custom_name]["actual_model_name"]
            g.token_manager.check_and_update_resetting_datetime(
                model_name=actual_model_name,
                limit_info_models=limit_info_models
            )
            limit_info_models[actual_model_name][provider].update(
                tokens_usage_dict.get(actual_model_name).get(provider))
            limit_info_models[actual_model_name][provider].update(MODELS_INFO_DICT["providers"][provider][custom_name])
            grouped_tokens_info.append({custom_name: {provider: limit_info_models[actual_model_name][provider]}})

        logger.success("Total tokens retrieved successfully.")
        return grouped_tokens_info
    except Exception as e:
        return create_error_response(f"Failed to get info tokens: {e}")


@chat_router.route("/general/v0/chats", methods=["GET"])
@setup_route
def get_user_chats(current_user):
    """Endpoint to retrieve all chats for the current user."""
    try:
        logger.info(f"Retrieving chats for user {current_user.email}.")
        resp = g.chat_manager.get_all(user_email=current_user.email)
        conversations = resp
        chats = [{"name": conv["_source"]["chat_name"], "id": conv["_id"]} for conv in conversations]
        logger.success("User chats retrieved successfully.")
        return jsonify(chats)
    except Exception as e:
        return create_error_response(f"Failed to retrieve user chats: {e}")


@chat_router.route("/general/v0/chats", methods=["POST"])
@setup_route
def new_chat(current_user):
    """Endpoint to create a new chat."""
    try:
        request_info = request.get_json()
        if not request_info:
            return create_error_response("Invalid JSON payload.", 400)

        payload = {"user": current_user.email,
                   "chat_name": request_info.get("chat_name", None),
                   "conversation": [],
                   "last_edit": datetime.now(timezone.utc).strftime(DATE_FORMAT),
                   "creation_date": datetime.now(timezone.utc).strftime(DATE_FORMAT)}

        resp = g.chat_manager.add(payload)
        if resp.get("result") == "created":
            response = {"id": resp["_id"], "name": request_info.get("chat_name")}
            logger.success(f"New chat {resp['_id']} created successfully.")
            return response_encoder.encode(response)

        return create_error_response("Failed to create new chat.")
    except Exception as e:
        return create_error_response(f"An error occurred while creating new chat: {e}")


@chat_router.route("/general/v0/chats/<chat_id>", methods=["GET"])
@setup_route
def retrieve_conversation(user, chat_id):
    """Endpoint to retrieve a conversation by its ID."""
    try:
        logger.info(f"Retrieving conversation {chat_id}.")
        conversation = g.chat_manager.get(user_email=str(user.email), chat_id=chat_id)
        return conversation
    except Exception as e:
        return create_error_response(f"Failed to retrieve conversation: {e}")


@chat_router.route("/general/v0/chats/<chat_id>", methods=["PATCH"])
@setup_route
def save_conversation(current_user, chat_id):
    """Endpoint to save/update a conversation."""
    try:
        json_full_chat = request.get_json()
        if not json_full_chat or not json_full_chat.get("conversation"):
            return create_error_response("Missing required fields: 'conversation'.", 400)

        payload = {
            "conversation": json_full_chat["conversation"],
            "last_edit": datetime.now(timezone.utc).strftime(DATE_FORMAT),
        }
        if json_full_chat.get("chat_name"):
            payload["chat_name"] = json_full_chat["chat_name"]
            logger.info("New chat_name has been submitted.")

        resp = g.chat_manager.save(chat_id, payload)
        logger.success(f"Conversation {chat_id} saved successfully.")
        return jsonpickle.encode(resp)
    except Exception as e:
        return create_error_response(f"Failed to save conversation: {e}")


@chat_router.route("/general/v0/chats/<chat_id>", methods=["DELETE"])
@setup_route
def delete_chat(current_user, chat_id):
    """Endpoint to delete a chat by its ID."""
    try:
        logger.info(f"Attempting to delete chat {chat_id}.")
        resp = g.chat_manager.delete(current_user.email, chat_id)
        logger.success(f"Chat {chat_id} deleted successfully.")
        return response_encoder.encode(resp), 200
    except Exception as e:
        return create_error_response(f"Failed to delete chat {chat_id}: {e}")


@chat_router.route("/general/v0/chats/<chat_id>/feedback", methods=["POST"])
@setup_route
def run_ingest_feedback(current_user, chat_id):
    """Endpoint to ingest user feedback."""
    try:
        feedback = request.get_json().get("feedback")
        if not feedback:
            return create_error_response("Feedback data is required.", 400)
        feedback["user_email"] = current_user.email
        feedback["timestamp"] = datetime.now(timezone.utc).strftime(DATE_FORMAT)
        logger.info(f"Saving feedback for chat {chat_id}.")
        response = g.feedback_manager.save(chat_id, feedback)
        logger.success("Feedback saved successfully.")
        return response
    except Exception as e:
        return create_error_response(f"Failed to save feedback: {e}")


def _validate_user_access(current_user: User, selected_model_name: str, selected_provider: str) -> None:
    """
    Checks user's trial status and token limits, raising an exception on failure.
    Uses services from the request global `g`.
    """
    user_info = g.user_repo.get(current_user.id)
    actual_model_name = MODELS_INFO_DICT["providers"][selected_provider][selected_model_name]["actual_model_name"]
    # Check trial expiration
    expiration_date = datetime.strptime(user_info.expiring_date_trial, DATE_FORMAT).date()
    if expiration_date < date.today():
        raise PermissionError("Your trial period has expired!")

    # Check and update token reset datetime
    limit_info_models = g.token_manager.get_limits_info_per_model(user_email=current_user.email,
                                                                     models_info_dict=MODELS_INFO_DICT)

    g.token_manager.check_and_update_resetting_datetime(model_name=actual_model_name,
                                                           limit_info_models=limit_info_models)

    # Check token limits
    token_info = g.token_manager.get_overall_tokens_usage_per_model(user_email=current_user.email,
                                                                       limit_info_models=limit_info_models)
    total_usage = sum(data.get("tot_tokens_timeframe", 0)
                      for model_data in token_info.values()
                      for data in model_data.values())
    if total_usage >= user_info.tot_token_limit:
        raise PermissionError("Overall tokens limit reached! Come back tomorrow :)")

    tot_tokens_timeframe = token_info.get(actual_model_name, {}).get(selected_provider, {}).get("tot_tokens_timeframe",
                                                                                                0)
    tokens_limit = limit_info_models.get(actual_model_name, {}).get(selected_provider, {}).get("tokens_limit", 0)
    if tot_tokens_timeframe >= tokens_limit:  # If triggered, you can edit limit in ES
        raise PermissionError(f"Tokens limit reached for model {selected_model_name}!")


def _prepare_chat_history(chat_manager,
                          conversation,
                          user_message: ChatMessage,
                          interaction_type: str,
                          checkpoint: int) -> List:
    """Initializes and returns the correct chat history based on the interaction type."""
    messages = conversation.get("messages", [])
    messages = messages[:checkpoint]
    chat_manager.initialize_chat(chat_history=messages)
    chat_history = chat_manager.get_chat_history()
    chat_history.append(user_message)
    chat_manager.chat_history_manager.set_history(chat_history)
    return chat_history


def _get_recorded_notes(conversation):
    messages = conversation.get("messages", [])
    return {k: v
            for m in messages
            if m.get("recorded_notes")
            for k, v in m["recorded_notes"].items()}


@chat_router.route("/general/v0/chats/<chat_id>/invoke", methods=["POST"])
@setup_route
def get_answer(current_user, chat_id):
    """Endpoint to invoke the conversation chain."""
    try:
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            _handle_chat_interaction(chat_id, current_user, request.get_json())
        )
        return result
    except Exception as e:
        if "ResponsibleAIPolicyViolation" in str(e):
            logger.warning("Harmful content detected!")
            return create_error_response("Harmful content detected in your prompt. Please modify it and retry.", 403)
        return create_error_response(f"Failed to get answer: {e}")


@DebugLogger.profile_static(logger=logger)
@trace_chat_turn
async def _handle_chat_interaction(chat_id: str,
                                   current_user: User,
                                   request_data: Dict[str, Any]):
    """
    Main handler for chat interactions. Orchestrates validation, setup, and response generation.
    Uses services from the request global `g`.
    """
    try:
        req = ChatInteractionRequest(**request_data)

        if not req.user_question:
            return create_error_response("'user_question' is required.", 400)
        if req.provider not in {"azure", "openai", "openrouter", "google", "ollama", "huggingface"}:
            return create_error_response("Unsupported model provider.", 400)
        if req.workflow not in {
            "ExampleQuestions", "FocusMode", "UserSupport", "QA", "Report",
            "AllForOne", "General", "DeepResearch",
        }:
            return create_error_response("Unsupported chat workflow.", 400)

        redactor = current_app.extensions["pii_redactor"]
        req.user_question = redactor.redact(req.user_question)
        guardrails = current_app.extensions["nemo_guardrails"]
        req.user_question = await guardrails.check_input(req.user_question)
        if req.assistant_answer:
            req.assistant_answer = redact_nested(req.assistant_answer, redactor)

        # Get main_agent from the request global `g`
        main_agent = g.main_agent
        main_agent.user = current_user.email

        # Initialization and Validation
        model_manager = ModelManager()
        model_manager.config_log(current_user.email)

        _validate_user_access(current_user=current_user,
                              selected_model_name=req.llm_model,
                              selected_provider=req.provider)

        # Get Language Model
        llm = model_manager.get_model({"custom_name": req.llm_model, "provider": req.provider})

        # Prepare Chat Context
        chat_manager = main_agent.get_new_chat_manager()
        user_message = chat_manager.chat_history_manager._create_user_message(user_query=req.user_question,
                                                                              selected_docs=req.selected_documents)
        conversation = g.chat_manager.get(user_email=str(current_user.email), chat_id=chat_id)
        conversation = redact_nested(conversation, redactor)

        recorded_notes = _get_recorded_notes(conversation=conversation)
        chat_history = _prepare_chat_history(chat_manager=chat_manager,
                                             user_message=user_message,
                                             interaction_type=req.invoke,
                                             checkpoint=req.checkpoint,
                                             conversation=conversation)

        logger.info(f"Received {req.invoke} request for chat '{chat_id}'.")

        # TODO Remove once FE implemented
        if str(req.user_question).startswith("!"):
            workflow = "AllForOne"
        elif str(req.user_question).startswith("?"):
            workflow = "ExampleQuestions"
        else:
            workflow = req.workflow  # QA

        req_info = {
            "chat_id": chat_id,
            "workflow": workflow,  # req.workflow,
            "chat_history": chat_history,
            "provider": req.provider,
            "user_roles": current_user.groups,
            "doc_search": req.doc_search,
            "web_search": req.web_search,
            "internal_knowledge": req.internal_knowledge,
            "selected_language": req.selected_language,
            "selected_documents": req.selected_documents,
            "selected_page_numbers": req.selected_page_numbers,
            "selected_chunk_numbers": req.selected_chunk_numbers,
            "prev_answer": ChatMessage(role="assistant",
                                       content=req.assistant_answer["content"],
                                       additional_kwargs={"sources": req.assistant_answer["sources"]}) if req.assistant_answer else None,
            "generate_chat_name": not req.chat_name,
            "provided_sources": [],  # provided_sources,
            "report_type": "free",  # req.report_type or "free" # default: "free"
            "recorded_notes": recorded_notes,
        }

        # Generate Answer
        response_generator = chat_manager.get_answer(llm=llm,
                                                     req_info=req_info)
        return await handle_streaming_response(
            response_generator,
            chat_id,
            req.socket_id,
            redactor,
            guardrails,
            req.workflow,
            req.user_question,
        )

    except GuardrailViolation as e:
        logger.warning(f"Guardrail blocked chat {chat_id} at {e.stage}.")
        return create_error_response("The request was blocked by the content safety policy.", 403)
    except (PermissionError, ValueError) as e:
        logger.warning(f"Access denied for user {current_user.email}: {e}")
        return create_error_response(str(e), 400)
    except Exception as e:
        logger.error(f"An unexpected error occurred for user {current_user.email}: {e}", exc_info=True)
        return create_error_response("An internal server error occurred.", 500)