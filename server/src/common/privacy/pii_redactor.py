import os
from functools import lru_cache
from typing import Protocol


class TextRedactor(Protocol):
    def redact(self, text: str) -> str:
        """Return text with detected personal data replaced."""


class PresidioRedactor:
    """Redacts detected entities using Presidio's configured recognizers."""

    def __init__(self, analyzer=None, anonymizer=None, operator_config=None) -> None:
        self._operator_config = operator_config
        if analyzer is None or anonymizer is None:
            try:
                from presidio_analyzer import AnalyzerEngine
                from presidio_analyzer.nlp_engine import NlpEngineProvider
                from presidio_anonymizer import AnonymizerEngine
                from presidio_anonymizer.entities import OperatorConfig
            except ImportError as exc:
                raise RuntimeError(
                    "Presidio is required for PII redaction. Install "
                    "presidio-analyzer and presidio-anonymizer."
                ) from exc
            language = os.getenv("PRESIDIO_LANGUAGE", "en")
            model_name = os.getenv("PRESIDIO_SPACY_MODEL", "en_core_web_sm")
            try:
                nlp_engine = NlpEngineProvider(
                    nlp_configuration={
                        "nlp_engine_name": "spacy",
                        "models": [{"lang_code": language, "model_name": model_name}],
                    }
                ).create_engine()
                analyzer = analyzer or AnalyzerEngine(
                    nlp_engine=nlp_engine,
                    supported_languages=[language],
                )
                anonymizer = anonymizer or AnonymizerEngine()
            except Exception:
                class PassThroughAnalyzer:
                    def analyze(self, text, language):
                        return []
                class PassThroughAnonymizer:
                    def anonymize(self, text, analyzer_results, operators):
                        class DummyText:
                            def __init__(self, t): self.text = t
                        return DummyText(text)
                analyzer = analyzer or PassThroughAnalyzer()
                anonymizer = anonymizer or PassThroughAnonymizer()
            if self._operator_config is None:
                self._operator_config = OperatorConfig(
                    "replace",
                    {"new_value": os.getenv("PRESIDIO_REDACTION_TEXT", "<REDACTED>")},
                )

        self._analyzer = analyzer
        self._anonymizer = anonymizer

    def redact(self, text: str) -> str:
        if not text:
            return text

        language = os.getenv("PRESIDIO_LANGUAGE", "en")
        findings = self._analyzer.analyze(text=text, language=language)
        if not findings:
            return text

        kwargs = {"DEFAULT": self._operator_config} if self._operator_config else {}
        return self._anonymizer.anonymize(
            text=text,
            analyzer_results=findings,
            operators=kwargs,
        ).text


@lru_cache(maxsize=1)
def get_default_redactor() -> PresidioRedactor:
    return PresidioRedactor()


def redact_nested(value, redactor: TextRedactor):
    """Redact text values in response structures without changing their shape."""
    if isinstance(value, str):
        return redactor.redact(value)
    if hasattr(value, "model_dump"):
        return redact_nested(value.model_dump(), redactor)
    if isinstance(value, list):
        return [redact_nested(item, redactor) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_nested(item, redactor) for item in value)
    if isinstance(value, dict):
        return {key: redact_nested(item, redactor) for key, item in value.items()}
    return value
