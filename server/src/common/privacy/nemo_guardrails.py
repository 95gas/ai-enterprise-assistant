import os
from pathlib import Path


class GuardrailViolation(Exception):
    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(f"NeMo Guardrails blocked {stage}.")


class NemoGuardrailsService:
    """Runs configured NeMo input and output rails around chat responses."""

    def __init__(self, rails=None) -> None:
        self._rails = rails
        self._rail_type = None
        if self._rails is not None:
            return

        enabled = os.getenv("NEMO_GUARDRAILS_ENABLED", "false").strip().lower()
        if enabled not in {"1", "true", "yes"}:
            return

        try:
            from nemoguardrails import LLMRails, RailsConfig
            from nemoguardrails.rails.llm.options import RailType
        except ImportError as exc:
            raise RuntimeError(
                "NeMo Guardrails is enabled but nemoguardrails is not installed."
            ) from exc

        config_path = Path(os.getenv(
            "NEMO_GUARDRAILS_CONFIG",
            str(Path(__file__).resolve().parents[2] / "config" / "guardrails"),
        ))
        if not config_path.exists():
            raise FileNotFoundError(
                f"NeMo Guardrails configuration not found: {config_path}"
            )
        self._rails = LLMRails(RailsConfig.from_path(str(config_path)))
        self._rail_type = RailType

    async def check_input(self, text: str) -> str:
        return await self._check(
            [{"role": "user", "content": text}],
            stage="input",
            original=text,
        )

    async def check_output(self, user_input: str, text: str) -> str:
        return await self._check(
            [
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": text},
            ],
            stage="output",
            original=text,
        )

    async def _check(self, messages, stage: str, original: str) -> str:
        if self._rails is None:
            return original

        rail_type = None
        if self._rail_type is not None:
            rail_type = [
                self._rail_type.INPUT if stage == "input" else self._rail_type.OUTPUT
            ]
        result = await self._rails.check_async(messages, rail_types=rail_type)
        status = getattr(result.status, "value", result.status)
        if status == "blocked":
            raise GuardrailViolation(stage)
        if status == "modified":
            if not isinstance(result.content, str):
                raise RuntimeError("NeMo Guardrails returned invalid modified content.")
            return result.content
        if status != "passed":
            raise RuntimeError(f"NeMo Guardrails returned unknown status: {status!r}")
        return original
