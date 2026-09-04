from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Finding, Review
from app.review.engine import run_review
from app.schemas import ReviewOut, ReviewRequest, ReviewSummary
from app.services.store import persist_review

router = APIRouter(prefix="/review", tags=["review"])


@router.post("", response_model=ReviewOut)
def create_review(req: ReviewRequest, db: Session = Depends(get_db)) -> Review:
    try:
        result = run_review(
            code=req.code,
            diff=req.diff,
            filename=req.filename,
            language=req.language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return persist_review(db, result, source="api")


@router.get("", response_model=list[ReviewSummary])
def list_reviews(db: Session = Depends(get_db), limit: int = 50) -> list[ReviewSummary]:
    count_sq = (
        select(Finding.review_id, func.count(Finding.id).label("n"))
        .group_by(Finding.review_id)
        .subquery()
    )
    rows = db.execute(
        select(Review, func.coalesce(count_sq.c.n, 0))
        .outerjoin(count_sq, count_sq.c.review_id == Review.id)
        .order_by(Review.id.desc())
        .limit(limit)
    ).all()
    return [
        ReviewSummary(
            id=r.id,
            created_at=r.created_at,
            source=r.source,
            engine=r.engine,
            language=r.language,
            tech_debt_score=r.tech_debt_score,
            finding_count=n,
        )
        for r, n in rows
    ]


@router.get("/{review_id}", response_model=ReviewOut)
def get_review(review_id: int, db: Session = Depends(get_db)) -> Review:
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return review
