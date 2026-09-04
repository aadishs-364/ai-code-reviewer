"""Thin wrapper around the Claude API.

The rest of the app never imports `anthropic` directly. It calls this service,
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


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None
        if self.settings.llm_enabled:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
            except Exception as exc:  # SDK missing or bad key format
                logger.warning("Claude API unavailable, using heuristics only: %s", exc)
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    # -- Review -------------------------------------------------------------

    def review(
        self, *, content: str, language: str | None, filename: str | None, is_diff: bool
    ) -> dict:
        """Return {"summary": str, "findings": [ {category, severity, ...} ]}.

        Raises if the API call fails so the caller can decide whether to fall
        back to heuristics.
        """
        assert self._client is not None
        user = prompts.build_review_user_prompt(
            language=language, filename=filename, content=content, is_diff=is_diff
        )
        response = self._client.messages.create(
            model=self.settings.anthropic_model,
            max_tokens=self.settings.anthropic_max_tokens,
            thinking={"type": "adaptive"},
            system=prompts.REVIEW_SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_config={
                "format": {"type": "json_schema", "schema": _REVIEW_SCHEMA}
            },
        )
        text = next((b.text for b in response.content if b.type == "text"), "{}")
        data = json.loads(text)
        for f in data.get("findings", []):
            f["origin"] = "llm"
        return data

    # -- Documentation ------------------------------------------------------

    def generate_docs(
        self, *, content: str, language: str | None, filename: str | None, style: str
    ) -> str:
        assert self._client is not None
        user = prompts.build_doc_user_prompt(
            language=language, filename=filename, content=content, style=style
        )
        # Docs can be long — stream and collect to avoid HTTP timeouts.
        with self._client.messages.stream(
            model=self.settings.anthropic_model,
            max_tokens=self.settings.anthropic_max_tokens,
            system=prompts.DOC_SYSTEM,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            message = stream.get_final_message()
        return "".join(b.text for b in message.content if b.type == "text")


_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
