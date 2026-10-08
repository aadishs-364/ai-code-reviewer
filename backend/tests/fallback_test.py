"""Retry + model-fallback test — no API key or network needed.

Run: python -m tests.fallback_test
Claude runs through the real SDK on a fake HTTP transport, so its retry
behaviour on 429 / 5xx / timeouts is the SDK's actual behaviour.
"""

from __future__ import annotations

import json

import anthropic
import httpx2 as httpx

from app.services.llm import LLMClient

OK_REVIEW = {"summary": "fine", "findings": []}


def make_client(claude_statuses: list, gemini_replies: list) -> tuple[LLMClient, list, list]:
    """claude_statuses: per-attempt HTTP status, or "timeout".
    gemini_replies: per-call reply text, or an Exception to raise."""
    claude_calls, gemini_calls = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        status = claude_statuses[len(claude_calls)]
        claude_calls.append(status)
        if status == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        if status != 200:
            return httpx.Response(status, headers={"retry-after-ms": "1"}, json={})
        return httpx.Response(200, json={
            "id": "m", "type": "message", "role": "assistant", "model": "claude",
            "content": [{"type": "text", "text": json.dumps(OK_REVIEW)}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    llm = LLMClient.__new__(LLMClient)
    llm.settings = type("S", (), {
        "anthropic_model": "claude", "anthropic_max_tokens": 10,
        "gemini_models": ["gemini-pro", "gemini-flash", "gemini-flash-old"],
    })()
    llm._claude = anthropic.Anthropic(
        api_key="test", max_retries=2,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    llm._gemini = object()  # only needs to be non-None

    def fake_gemini(model, system, user, schema=None):
        reply = gemini_replies[len(gemini_calls)]
        gemini_calls.append(model)
        if isinstance(reply, Exception):
            raise reply
        return reply

    llm._gemini_text = fake_gemini
    return llm, claude_calls, gemini_calls


def review(llm):
    return llm.review(content="x = 1", language="python", filename="a.py", is_diff=False)


def test_retry_then_success():
    llm, c, g = make_client([429, 503, 200], [])
    assert review(llm)["summary"] == "fine"
    assert c == [429, 503, 200] and g == []


def test_retries_exhausted_falls_back_in_order():
    llm, c, g = make_client(
        [500, "timeout", 529], [RuntimeError("down"), json.dumps(OK_REVIEW)]
    )
    assert review(llm)["summary"] == "fine"
    assert len(c) == 3  # 1 try + 2 retries, then fallback
    assert g == ["gemini-pro", "gemini-flash"]  # stops at first success


def test_non_retryable_not_retried():
    llm, c, g = make_client([401], [json.dumps(OK_REVIEW)])
    review(llm)
    assert c == [401] and g == ["gemini-pro"]


def test_bad_json_falls_back():
    llm, c, g = make_client([401], ["not json", json.dumps(OK_REVIEW)])
    review(llm)
    assert g == ["gemini-pro", "gemini-flash"]


def test_all_fail_raises():
    llm, c, g = make_client([400], [RuntimeError("a"), RuntimeError("b"), RuntimeError("c")])
    try:
        review(llm)
    except RuntimeError as exc:
        assert str(exc) == "c"
    else:
        raise AssertionError("expected failure")
    assert g == ["gemini-pro", "gemini-flash", "gemini-flash-old"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
