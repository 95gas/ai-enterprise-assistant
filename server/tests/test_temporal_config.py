from src.services.chat.temporal import temporal_enabled


def test_temporal_is_opt_in(monkeypatch):
    monkeypatch.delenv("TEMPORAL_ENABLED", raising=False)
    assert temporal_enabled() is False

    monkeypatch.setenv("TEMPORAL_ENABLED", "true")
    assert temporal_enabled() is True
