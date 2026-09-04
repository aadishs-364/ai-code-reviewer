"""Technical-debt scoring derived from review findings.

Produces a single 0-100 score (higher = more debt) so reviews are comparable
over time and can gate a PR. The weighting is deliberately simple and
transparent rather than a black box.
"""

from __future__ import annotations

_SEVERITY_WEIGHT = {
    "critical": 25.0,
    "high": 12.0,
    "medium": 5.0,
    "low": 2.0,
    "info": 0.5,
}

# Security issues weigh more toward the debt/risk score than style nits.
_CATEGORY_MULTIPLIER = {
    "security": 1.5,
    "performance": 1.1,
    "design": 1.0,
    "tech_debt": 1.0,
    "style": 0.5,
}


def compute_tech_debt_score(findings: list[dict]) -> float:
    """Return a 0-100 score. Saturating so a few criticals dominate."""
    raw = 0.0
    for f in findings:
        sev = _SEVERITY_WEIGHT.get(f.get("severity", "info"), 0.5)
        mult = _CATEGORY_MULTIPLIER.get(f.get("category", "design"), 1.0)
        raw += sev * mult
    # Map unbounded raw penalty onto 0-100 with diminishing returns.
    score = 100.0 * (1.0 - 1.0 / (1.0 + raw / 40.0))
    return round(score, 1)


def refactor_candidates(findings: list[dict]) -> list[dict]:
    """Subset of findings most worth refactoring, highest severity first."""
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    candidates = [
        f
        for f in findings
        if f.get("category") in ("tech_debt", "design", "performance")
    ]
    candidates.sort(key=lambda f: order.get(f.get("severity", "info"), 5))
    return candidates
