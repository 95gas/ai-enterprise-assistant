import logging
import os
import time
from contextlib import contextmanager
from functools import wraps

_telemetry_state = None
_WORKFLOW_LABELS = {
    "ExampleQuestions", "FocusMode", "UserSupport", "QA", "Report",
    "AllForOne", "General", "DeepResearch",
}
_PROVIDER_LABELS = {"azure", "openai", "openrouter", "google", "ollama", "huggingface"}


class ChatTelemetry:
    def __init__(self, tracer, meter) -> None:
        self.tracer = tracer
        self._latency = meter.create_histogram(
            "ask.chat.duration",
            unit="s",
            description="End-to-end chat generation latency",
        )
        self._tokens = meter.create_counter(
            "ask.llm.tokens",
            unit="token",
            description="LLM token usage by direction",
        )
        self._requests = meter.create_counter(
            "ask.chat.requests",
            unit="request",
            description="Number of completed chat request attempts",
        )
        self._errors = meter.create_counter(
            "ask.chat.errors",
            unit="request",
            description="Number of failed chat request attempts",
        )

    @contextmanager
    def chat_turn(self, workflow: str, provider: str):
        started = time.perf_counter()
        attributes = {"workflow": workflow, "provider": provider}
        self._requests.add(1, attributes)
        with self.tracer.start_as_current_span("chat.turn") as span:
            span.set_attribute("chat.workflow", workflow)
            span.set_attribute("llm.provider", provider)
            try:
                yield
            except Exception as exc:
                from opentelemetry.trace import Status, StatusCode

                span.set_attribute("error.type", type(exc).__name__)
                span.set_status(Status(StatusCode.ERROR))
                self._errors.add(1, attributes)
                raise
            finally:
                self._latency.record(time.perf_counter() - started, attributes)

    def record_tokens(self, input_tokens: int, output_tokens: int, workflow: str) -> None:
        attributes = {"workflow": workflow}
        if input_tokens > 0:
            self._tokens.add(input_tokens, {**attributes, "direction": "input"})
        if output_tokens > 0:
            self._tokens.add(output_tokens, {**attributes, "direction": "output"})


def configure_telemetry(app):
    """Set up opt-in OTLP traces/logs and a Prometheus scrape endpoint."""
    global _telemetry_state
    enabled = os.getenv("OTEL_ENABLED", "false").strip().lower() in {"1", "true", "yes"}
    if not enabled:
        app.extensions["telemetry"] = None
        return None

    if _telemetry_state is not None:
        _instrument_app(app, _telemetry_state["registry"])
        app.extensions["telemetry"] = _telemetry_state["telemetry"]
        return _telemetry_state["telemetry"]

    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from prometheus_client import CollectorRegistry, CONTENT_TYPE_LATEST, generate_latest
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    from flask import Response

    resource = Resource.create({
        "service.name": os.getenv("OTEL_SERVICE_NAME", "ask-server"),
        "deployment.environment": os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT", "development"),
    })
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    prometheus_registry = CollectorRegistry()
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PrometheusMetricReader(registry=prometheus_registry)],
    )
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    set_logger_provider(logger_provider)
    otel_logger = logging.getLogger("ask.telemetry")
    otel_logger.propagate = False
    otel_logger.setLevel(logging.DEBUG)
    otel_logger.addHandler(LoggingHandler(logger_provider=logger_provider))

    _instrument_app(app, prometheus_registry)
    telemetry = ChatTelemetry(
        tracer=trace.get_tracer("ask.chat"),
        meter=metrics.get_meter("ask.chat"),
    )
    _telemetry_state = {
        "registry": prometheus_registry,
        "telemetry": telemetry,
    }
    app.extensions["telemetry"] = telemetry
    return telemetry


def configure_fastapi_metrics(app, service_name):
    """Expose request and process metrics for a standalone FastAPI service."""
    from fastapi.responses import Response
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        GCCollector,
        Histogram,
        PlatformCollector,
        ProcessCollector,
        generate_latest,
    )

    registry = CollectorRegistry()
    ProcessCollector(registry=registry)
    PlatformCollector(registry=registry)
    GCCollector(registry=registry)
    requests = Counter(
        "http_server_requests_total",
        "HTTP requests served by the application",
        ["service", "method", "route", "status"],
        registry=registry,
    )
    duration = Histogram(
        "http_server_request_duration_seconds",
        "HTTP request duration in seconds",
        ["service", "method", "route"],
        registry=registry,
    )

    @app.middleware("http")
    async def record_http_metrics(request, call_next):
        started = time.perf_counter()
        method = request.method
        try:
            response = await call_next(request)
        except Exception:
            route = request.scope.get("route")
            route_name = getattr(route, "path", "unmatched")
            requests.labels(service_name, method, route_name, "500").inc()
            duration.labels(service_name, method, route_name).observe(
                time.perf_counter() - started
            )
            raise

        route = request.scope.get("route")
        route_name = getattr(route, "path", "unmatched")
        requests.labels(
            service_name, method, route_name, str(response.status_code)
        ).inc()
        duration.labels(service_name, method, route_name).observe(
            time.perf_counter() - started
        )
        return response

    async def metrics_response():
        return Response(
            content=generate_latest(registry),
            media_type=CONTENT_TYPE_LATEST,
        )

    app.add_api_route(
        "/metrics",
        metrics_response,
        methods=["GET"],
        include_in_schema=False,
        name="prometheus_metrics",
    )
    return registry


def _instrument_app(app, prometheus_registry):
    from flask import Response
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    FlaskInstrumentor().instrument_app(app, request_hook=_scrub_http_request)
    app.add_url_rule(
        "/metrics",
        "prometheus_metrics",
        lambda: Response(
            generate_latest(prometheus_registry),
            content_type=CONTENT_TYPE_LATEST,
        ),
        methods=["GET"],
    )


def _scrub_http_request(span, environ):
    path = environ.get("PATH_INFO", "")
    segments = path.split("/")
    sensitive_resources = {"chats", "documents", "approvals", "users"}
    for index in range(1, len(segments)):
        if segments[index - 1] in sensitive_resources and segments[index]:
            segments[index] = "{id}"
    safe_path = "/".join(segments)
    scheme = environ.get("wsgi.url_scheme", "http")
    host = environ.get("HTTP_HOST", environ.get("SERVER_NAME", "localhost"))
    safe_url = f"{scheme}://{host}{safe_path}"
    span.set_attribute("url.path", safe_path)
    span.set_attribute("url.full", safe_url)
    span.set_attribute("http.url", safe_url)
    span.set_attribute("http.target", safe_path)
    span.set_attribute("url.query", "")


def trace_chat_turn(function):
    @wraps(function)
    async def wrapper(chat_id, current_user, request_data, *args, **kwargs):
        from flask import current_app

        telemetry = current_app.extensions.get("telemetry")
        if telemetry is None:
            return await function(chat_id, current_user, request_data, *args, **kwargs)
        requested_workflow = request_data.get("workflow") if isinstance(request_data, dict) else None
        requested_provider = request_data.get("provider") if isinstance(request_data, dict) else None
        with telemetry.chat_turn(
            workflow=requested_workflow if requested_workflow in _WORKFLOW_LABELS else "unknown",
            provider=requested_provider if requested_provider in _PROVIDER_LABELS else "unknown",
        ):
            return await function(chat_id, current_user, request_data, *args, **kwargs)

    return wrapper


def trace_rag_retrieval(function):
    @wraps(function)
    async def wrapper(*args, **kwargs):
        from opentelemetry import metrics, trace
        from opentelemetry.trace import Status, StatusCode

        tracer = trace.get_tracer("ask.rag")
        meter = metrics.get_meter("ask.rag")
        duration = meter.create_histogram(
            "ask.rag.duration",
            unit="s",
            description="RAG retrieval latency",
        )
        results = meter.create_histogram(
            "ask.rag.results",
            unit="{result}",
            description="Number of chunks returned by RAG retrieval",
        )
        started = time.perf_counter()
        with tracer.start_as_current_span("rag.retrieve") as span:
            try:
                nodes = await function(*args, **kwargs)
            except Exception as exc:
                span.set_attribute("error.type", type(exc).__name__)
                span.set_status(Status(StatusCode.ERROR))
                duration.record(time.perf_counter() - started)
                results.record(0, {"outcome": "error"})
                raise
            span.set_attribute("rag.result_count", len(nodes))
            duration.record(time.perf_counter() - started)
            results.record(len(nodes), {
                "outcome": "empty" if not nodes else "found",
            })
            return nodes

    return wrapper
