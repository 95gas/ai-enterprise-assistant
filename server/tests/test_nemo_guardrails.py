import asyncio
from types import SimpleNamespace

import pytest

from src.common.privacy.nemo_guardrails import (
    GuardrailViolation,
    NemoGuardrailsService,
)


class FakeRails:
    def __init__(self, status, content):
        self.status = status
        self.content = content
        self.calls = []

    async def check_async(self, messages, rail_types=None):
        self.calls.append((messages, rail_types))
        return SimpleNamespace(
            status=SimpleNamespace(value=self.status),
            content=self.content,
        )


def test_disabled_nemo_guardrails_leave_text_unchanged(monkeypatch):
    monkeypatch.delenv("NEMO_GUARDRAILS_ENABLED", raising=False)
    service = NemoGuardrailsService()

    assert asyncio.run(service.check_input("hello")) == "hello"
    assert asyncio.run(service.check_output("hello", "answer")) == "answer"


def test_nemo_guardrails_return_modified_text():
    rails = FakeRails("modified", "safe replacement")
    service = NemoGuardrailsService(rails=rails)

    assert asyncio.run(service.check_input("unsafe input")) == "safe replacement"
    assert rails.calls[0][0] == [{"role": "user", "content": "unsafe input"}]
    assert rails.calls[0][1] is None


def test_nemo_guardrails_raise_for_blocked_input_or_output():
    rails = FakeRails("blocked", "")
    service = NemoGuardrailsService(rails=rails)

    with pytest.raises(GuardrailViolation) as input_error:
        asyncio.run(service.check_input("blocked"))
    assert input_error.value.stage == "input"

    with pytest.raises(GuardrailViolation) as output_error:
        asyncio.run(service.check_output("question", "blocked"))
    assert output_error.value.stage == "output"
