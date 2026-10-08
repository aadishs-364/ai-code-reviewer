"""Thin wrapper around the Claude and Gemini APIs.

The rest of the app never imports an LLM SDK directly. It calls this service,
which reports `available` so callers can transparently fall back to the local
heuristic engine when no API key is configured (or the SDK isn't installed).
"""

from __future__ import annotations

import json
import logging

from app.config import get_settings
from app.review import prompts

logger = logging.getLogger(__name__)

# JSON schema the model must fill for a structured review. Kept to types the
# structured-output feature supports (no min/max constraints).
_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["security", "performance", "design", "tech_debt", "style"],
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low", "info"],
                    },
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "suggestion": {"type": "string"},
                    "line": {"type": ["integer", "null"]},
                },
                "required": ["category", "severity", "title", "detail", "suggestion", "line"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "findings"],
    "additionalProperties": False,
}


_RETRY_STATUS = [429, 500, 502, 503, 504, 529]


def _claude_text(message) -> str:
    """Text of a Claude reply. A refusal arrives as HTTP 200, so raise to
    make the fallback chain move on instead of returning an empty review."""
    if message.stop_reason == "refusal":
        raise RuntimeError("Claude declined the request")
    return "".join(b.text for b in message.content if b.type == "text")


class LLMClient:
    """Tries Claude, then each Gemini model in order. Each SDK retries
    retryable errors (429/5xx/network) with backoff; once a model's retries
    are exhausted, or it fails outright, the next model is tried."""

    def __init__(self) -> None:
        self.settings = get_settings()
        s = self.settings
        self._claude = None
        self._gemini = None
        if s.anthropic_api_key:
            try:
                import anthropic

                self._claude = anthropic.Anthropic(
                    api_key=s.anthropic_api_key,
                    timeout=s.llm_timeout_seconds,
                    max_retries=s.llm_max_retries,
                )
            except Exception as exc:  # SDK missing or bad key format
                logger.warning("Claude API unavailable: %s", exc)
        if s.gemini_api_key:
            try:
                from google import genai
                from google.genai import types

                self._gemini = genai.Client(
                    api_key=s.gemini_api_key,
                    http_options=types.HttpOptions(
                        timeout=int(s.llm_timeout_seconds * 1000),
                        retry_options=types.HttpRetryOptions(
                            attempts=s.llm_max_retries + 1,
                            http_status_codes=_RETRY_STATUS,
                        ),
                    ),
                )
            except Exception as exc:
                logger.warning("Gemini API unavailable: %s", exc)

    @property
    def available(self) -> bool:
        return self._claude is not None or self._gemini is not None

    def _models(self) -> list[str]:
        models = [self.settings.anthropic_model] if self._claude else []
        if self._gemini:
            models += self.settings.gemini_models
        return models

    def _with_fallback(self, task: str, call):
        """Run call(model) down the chain; return the first success."""
        models = self._models()
        for i, model in enumerate(models):
            try:
                result = call(model)
                if i:
                    logger.info("%s answered by fallback model %s", task, model)
                return result
            except Exception as exc:
                # Log the error type/status only, never the prompt.
                logger.warning("%s failed on %s (%s); trying next model",
                               task, model, type(exc).__name__)
                last = exc
        raise last

    def _gemini_text(self, model: str, system: str, user: str, schema=None) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(system_instruction=system)
        if schema:
            config.response_mime_type = "application/json"
            config.response_json_schema = schema
        return self._gemini.models.generate_content(
            model=model, contents=user, config=config
        ).text or ""

    # -- Review -------------------------------------------------------------

    def review(
        self, *, content: str, language: str | None, filename: str | None, is_diff: bool
    ) -> dict:
        """Return {"summary": str, "findings": [ {category, severity, ...} ]}.

        Raises if every model fails so the caller can fall back to heuristics.
        """
        assert self.available
        user = prompts.build_review_user_prompt(
            language=language, filename=filename, content=content, is_diff=is_diff
        )

        def call(model: str) -> str:
            if model.startswith("gemini"):
                return self._gemini_text(model, prompts.REVIEW_SYSTEM, user, _REVIEW_SCHEMA)
            response = self._claude.messages.create(
                model=model,
                max_tokens=self.settings.anthropic_max_tokens,
                thinking={"type": "adaptive"},
                system=prompts.REVIEW_SYSTEM,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "format": {"type": "json_schema", "schema": _REVIEW_SCHEMA}
                },
            )
            return _claude_text(response)

        # Parse inside the chain so a malformed JSON reply also falls back.
        data = self._with_fallback("review", lambda m: json.loads(call(m)))
        for f in data.get("findings", []):
            f["origin"] = "llm"
        return data

    # -- Documentation ------------------------------------------------------

    def generate_docs(
        self, *, content: str, language: str | None, filename: str | None, style: str
    ) -> str:
        assert self.available
        user = prompts.build_doc_user_prompt(
            language=language, filename=filename, content=content, style=style
        )

        def call(model: str) -> str:
            if model.startswith("gemini"):
                return self._gemini_text(model, prompts.DOC_SYSTEM, user)
            # Docs can be long — stream and collect to avoid HTTP timeouts.
            # Nothing reaches the user until the full message arrives, so
            # falling back after a mid-stream failure is safe.
            with self._claude.messages.stream(
                model=model,
                max_tokens=self.settings.anthropic_max_tokens,
                system=prompts.DOC_SYSTEM,
                messages=[{"role": "user", "content": user}],
            ) as stream:
                message = stream.get_final_message()
            return _claude_text(message)

        return self._with_fallback("docs", call)


_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
