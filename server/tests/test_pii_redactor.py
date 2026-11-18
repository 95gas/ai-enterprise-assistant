from dataclasses import dataclass
from pydantic import BaseModel

from src.common.privacy.pii_redactor import PresidioRedactor, redact_nested


@dataclass
class Finding:
    start: int
    end: int


@dataclass
class AnonymizedText:
    text: str


class FakeAnalyzer:
    def analyze(self, text, language):
        assert language == "en"
        start = text.find("person@example.com")
        return [Finding(start, start + len("person@example.com"))] if start >= 0 else []


class FakeAnonymizer:
    def anonymize(self, text, analyzer_results, operators):
        finding = analyzer_results[0]
        replacement = operators["DEFAULT"].params["new_value"]
        return AnonymizedText(text[:finding.start] + replacement + text[finding.end:])


class ReplaceOperator:
    def __init__(self, params):
        self.params = params


def test_redacts_detected_text(monkeypatch):
    monkeypatch.setenv("PRESIDIO_REDACTION_TEXT", "[redacted]")
    redactor = PresidioRedactor(
        FakeAnalyzer(),
        FakeAnonymizer(),
        ReplaceOperator({"new_value": "[redacted]"}),
    )

    assert redactor.redact("Contact person@example.com today") == "Contact [redacted] today"


def test_returns_unchanged_text_when_no_entity_is_detected():
    redactor = PresidioRedactor(FakeAnalyzer(), FakeAnonymizer(), ReplaceOperator({}))

    assert redactor.redact("No personal data") == "No personal data"


def test_empty_text_does_not_call_engines():
    class UnexpectedAnalyzer:
        def analyze(self, **kwargs):
            raise AssertionError("analyzer should not be called for empty input")

    redactor = PresidioRedactor(
        UnexpectedAnalyzer(),
        FakeAnonymizer(),
        ReplaceOperator({}),
    )

    assert redactor.redact("") == ""


def test_redacts_strings_recursively_without_changing_response_shape():
    redactor = PresidioRedactor(
        FakeAnalyzer(),
        FakeAnonymizer(),
        ReplaceOperator({"new_value": "<REDACTED>"}),
    )
    payload = {
        "answer": "Contact person@example.com",
        "sources": [{"text": "No personal data", "reference_id": 1}],
        "tokens": 7,
    }

    assert redact_nested(payload, redactor) == {
        "answer": "Contact <REDACTED>",
        "sources": [{"text": "No personal data", "reference_id": 1}],
        "tokens": 7,
    }


def test_redacts_pydantic_response_models():
    class Model(BaseModel):
        answer: str

    redactor = PresidioRedactor(
        FakeAnalyzer(),
        FakeAnonymizer(),
        ReplaceOperator({"new_value": "<REDACTED>"}),
    )

    assert redact_nested(Model(answer="person@example.com"), redactor) == {
        "answer": "<REDACTED>",
    }
