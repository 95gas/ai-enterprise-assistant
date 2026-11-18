from src.common.telemetry import _scrub_http_request, configure_telemetry


class FakeSpan:
    def __init__(self):
        self.attributes = {}

    def set_attribute(self, key, value):
        self.attributes[key] = value


def test_scrub_http_request_removes_resource_ids_and_query_data():
    span = FakeSpan()

    _scrub_http_request(span, {
        "PATH_INFO": "/general/v0/chats/private-chat-id/invoke",
        "QUERY_STRING": "email=person%40example.com",
    })

    assert span.attributes == {
        "url.path": "/general/v0/chats/{id}/invoke",
        "url.full": "http://localhost/general/v0/chats/{id}/invoke",
        "http.url": "http://localhost/general/v0/chats/{id}/invoke",
        "http.target": "/general/v0/chats/{id}/invoke",
        "url.query": "",
    }


def test_telemetry_is_disabled_by_default(monkeypatch):
    class FakeApp:
        extensions = {}

    monkeypatch.delenv("OTEL_ENABLED", raising=False)
    app = FakeApp()

    assert configure_telemetry(app) is None
    assert app.extensions["telemetry"] is None
