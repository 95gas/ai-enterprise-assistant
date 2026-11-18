import os, logging, warnings
from flask import Flask, json, render_template, request
from flask_cors import CORS
from flask_socketio import SocketIO
from werkzeug.exceptions import HTTPException
from datetime import timedelta

# Import your routes and managers
from api.conversation import chat_router
from api.ingest import ingest_router
from api.login import login_router, login_manager

from src.common.logging.logger import DebugLogger
from src.common.privacy.pii_redactor import get_default_redactor
from src.common.privacy.nemo_guardrails import NemoGuardrailsService
from src.common.telemetry import configure_telemetry
from src.services.chat.temporal import TemporalAgentLoopClient, temporal_enabled
from src.common.models.llama_config import LIConfig
from src.services.rag.orchestrator import get_main_agent
from config.settings import settings

ORIGINS = settings.system.allowed_origins
PORT = settings.system.port

def disable_external_loggers():
    """Disabling third libs loggers"""
    warnings_lst = ["elastic_transport.transport", # Elasticsearch logger
                    "neo4j.notifications", # Neo4j logger
                    "uvicorn.error" # Uvicorn logger
                    "werkzeug", # SocketIO logger
                    "httpx" # Uvicorn logger
                    ]
    for w in warnings_lst:
        logging.getLogger(w).disabled = True
    warnings.filterwarnings("ignore")


# --- Define Filters and Global Variables ---

# Filter out healthcheck and metrics noise
class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/healthcheck" not in record.getMessage()


class MetricsCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/metrics" not in record.getMessage()


logging.getLogger("gunicorn.access").addFilter(HealthCheckFilter())
logging.getLogger("gunicorn.access").addFilter(MetricsCheckFilter())

# Initialize Flask-socketio
socketio = SocketIO()

# Initialize DebugLogger
logger = DebugLogger(user="undefined", class_name="app", main_feature="SYSTEM")
disable_external_loggers()

# --- Application Factory Function ---

def create_app(main_agent_instance=None, pii_redactor=None, nemo_guardrails=None):
    """
    Creates and configures the Flask application.
    This pattern is safer for multiprocessing and testing.
    """
    # Config Llama Index
    if main_agent_instance is None:
        logger.info("Configuring Llama Index...")
        LIConfig()
        logger.info("Initializing Main RAG Agent...")
        main_agent = get_main_agent()
    else:
        main_agent = main_agent_instance

    # Create Flask app
    app = Flask(__name__)
    app.secret_key = os.urandom(24)
    app.extensions["pii_redactor"] = pii_redactor or get_default_redactor()
    app.extensions["nemo_guardrails"] = nemo_guardrails or NemoGuardrailsService()
    app.extensions["temporal_agent_loop"] = (
        TemporalAgentLoopClient() if temporal_enabled() else None
    )

    # ATTACH THE AGENT TO THE APP CONTEXT
    app.main_agent = main_agent

    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(hours=24), # Absolute lifetime of the session cookie
        SESSION_REFRESH_EACH_REQUEST=True, # This enforces an sliding timeout (on every request) instead of a absolute one
    )

    # Initialize Flask-Login
    login_manager.init_app(app)
    
    app.config.update(
        REMEMBER_COOKIE_DURATION=timedelta(hours=24),
        REMEMBER_COOKIE_REFRESH_EACH_REQUEST=False,  # keep it absolute
    )
    
    # Set CORS
    CORS(app, origins=ORIGINS, methods=["GET", "POST", "OPTIONS", "DELETE"])
    socketio.init_app(app, cors_allowed_origins=ORIGINS)
    configure_telemetry(app)

    # --- Error Handlers ---
    @app.errorhandler(HTTPException)
    async def http_error_handler(e):
        """Return JSON instead of HTML for HTTP errors."""
        response = e.get_response()
        response.data = json.dumps({
            "code": e.code,
            "name": e.name,
            "description": e.description,
        })
        response.content_type = "application/json"
        return response

    @app.errorhandler(500)
    async def internal_server_error(e):
        return render_template("500.html"), 500

    @app.errorhandler(404)
    async def page_not_found(e):
        return render_template("404.html"), 404

    @login_manager.unauthorized_handler
    def unauthorized_handler():
        return {"message": "Unauthorized request"}, 401

    # --- Routes ---
    app.register_blueprint(login_router)
    app.register_blueprint(ingest_router)
    app.register_blueprint(chat_router)

    @app.route("/healthcheck", methods=["GET"])
    def healthcheck():
        return {"healthcheck": "HEALTHCHECK STATUS: EVERYTHING OK!"}

    # --- SocketIO Handlers ---
    @socketio.on('connect')
    def on_connect():
        logger.info(f"New socket connection established with id {request.sid}")

    @socketio.on_error()
    def error_handler(e):
        logger.error(f"Socket connection failed due to {request.event['message']}")

    return app


# --- Main Execution Block ---
if __name__ == "__main__":
    app = create_app()
    logger.info(f"Starting server on port {PORT}")
    socketio.run(app, host="0.0.0.0", port=PORT, allow_unsafe_werkzeug=True)