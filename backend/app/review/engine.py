"""Review orchestration.

Ties together: language detection, diff parsing, the heuristic engine, and the
optional Claude-backed reviewer. The heuristic baseline always runs; the LLM
layer augments it when a key is configured and gracefully degrades otherwise.
"""

from __future__ import annotations

import logging
import os

from app.review import docgen, heuristics, techdebt
from app.services.diff_parser import parse_unified_diff
from app.services.llm import get_llm

logger = logging.getLogger(__name__)


def detect_language(filename: str | None, override: str | None) -> str | None:
    if override:
        return override
    if not filename:
        return None
    _, ext = os.path.splitext(filename)
    return heuristics.LANGUAGE_BY_EXT.get(ext.lower())


def _dedupe(findings: list[dict]) -> list[dict]:
    """Drop near-duplicate findings (same category+line+title)."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for f in findings:
        key = (f.get("category"), f.get("line"), f.get("title"))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def run_review(
    *,
    code: str | None,
    diff: str | None,
    filename: str | None,
    language: str | None,
) -> dict:
    if not code and not diff:
        raise ValueError("Provide either `code` or `diff`.")

    lang = detect_language(filename, language)
    is_diff = diff is not None
    heuristic_findings: list[dict] = []

    if is_diff:
        for file_diff in parse_unified_diff(diff):
            lines = [(a.line_no, a.text) for a in file_diff.added]
            file_lang = detect_language(file_diff.path, language) or lang
            for f in heuristics.scan_lines(lines, file_lang):
                f["file_path"] = file_diff.path
                heuristic_findings.append(f)
        review_content = diff
    else:
        numbered = list(enumerate(code.splitlines(), start=1))
        heuristic_findings += heuristics.scan_lines(numbered, lang)
        if lang == "python":
            heuristic_findings += heuristics.scan_python_blocks(code)
        review_content = code

    llm = get_llm()
    engine = "heuristic"
    summary: str | None = None
    llm_findings: list[dict] = []

    if llm.available:
        try:
            result = llm.review(
                content=review_content,
                language=lang,
                filename=filename,
                is_diff=is_diff,
            )
            summary = result.get("summary")
            llm_findings = result.get("findings", [])
            engine = "llm"
        except Exception as exc:
            logger.warning("LLM review failed, using heuristics only: %s", exc)

    findings = _dedupe(llm_findings + heuristic_findings)
    findings.sort(key=lambda f: _SEV_ORDER.get(f.get("severity", "info"), 5))

    score = techdebt.compute_tech_debt_score(findings)
    if summary is None:
        summary = _heuristic_summary(findings, score)

    return {
        "engine": engine,
        "language": lang,
        "summary": summary,
        "findings": findings,
        "tech_debt_score": score,
    }


def run_docs(*, code: str, filename: str | None, language: str | None, style: str) -> dict:
    lang = detect_language(filename, language)
    llm = get_llm()
    if llm.available:
        try:
            doc = llm.generate_docs(
                content=code, language=lang, filename=filename, style=style
            )
            return {"engine": "llm", "language": lang, "documentation": doc}
        except Exception as exc:
            logger.warning("LLM doc generation failed, using heuristics: %s", exc)
    doc = docgen.generate_docs(content=code, language=lang, filename=filename)
    return {"engine": "heuristic", "language": lang, "documentation": doc}


def _heuristic_summary(findings: list[dict], score: float) -> str:
    if not findings:
        return "No issues detected by the static analysis engine."
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    parts = [f"{n} {sev}" for sev, n in counts.items()]
    return (
        f"Found {len(findings)} issue(s): "
        + ", ".join(parts)
        + f". Tech-debt score: {score}/100."
    )
