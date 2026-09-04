"""Persistence helpers shared by the API routers and the webhook worker."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Finding, Review


def persist_review(
    db: Session,
    result: dict,
    *,
    source: str = "api",
    repo: str | None = None,
    pr_number: int | None = None,
    commit_sha: str | None = None,
) -> Review:
    review = Review(
        source=source,
        language=result.get("language"),
        engine=result.get("engine", "heuristic"),
        summary=result.get("summary"),
        tech_debt_score=result.get("tech_debt_score"),
        repo=repo,
        pr_number=pr_number,
        commit_sha=commit_sha,
    )
    for f in result.get("findings", []):
        review.findings.append(
            Finding(
                category=f.get("category", "design"),
                severity=f.get("severity", "info"),
                title=f.get("title", ""),
                detail=f.get("detail", ""),
                suggestion=f.get("suggestion"),
                file_path=f.get("file_path"),
                line=f.get("line"),
                origin=f.get("origin", "heuristic"),
            )
        )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review
