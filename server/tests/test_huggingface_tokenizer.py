import sys
from types import SimpleNamespace
from unittest.mock import Mock

from src.common.models.tokenizer import TokenCounter


def test_huggingface_provider_uses_local_model_tokenizer(monkeypatch):
    configured_name = "demo_chat"
    actual_name = "google/gemma-3-270m-it"
    TokenCounter._instances.pop(("huggingface", configured_name), None)

    class FakeAutoTokenizer:
        @staticmethod
        def from_pretrained(name):
            assert name == actual_name
            return SimpleNamespace(encode=lambda text: text.split())

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoTokenizer=FakeAutoTokenizer),
    )

    counter = TokenCounter(provider="huggingface", model_name=configured_name, logger=Mock())
    assert counter.count("local model token count") == 4
    TokenCounter._instances.pop(("huggingface", configured_name), None)
