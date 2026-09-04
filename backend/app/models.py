from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    # Where the review came from: "api", "github_pr", etc.
    source: Mapped[str] = mapped_column(String(32), default="api")
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # GitHub context (nullable for plain API reviews)
    repo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Which engine produced this: "llm" or "heuristic"
    engine: Mapped[str] = mapped_column(String(16), default="heuristic")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tech_debt_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    findings: Mapped[list["Finding"]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
    )


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id"))

    # security | performance | design | tech_debt | style
    category: Mapped[str] = mapped_column(String(32))
    # critical | high | medium | low | info
    severity: Mapped[str] = mapped_column(String(16))

    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str] = mapped_column(Text)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)

    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    line: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # "llm" or "heuristic" — lets the UI show provenance
    origin: Mapped[str] = mapped_column(String(16), default="heuristic")

    review: Mapped["Review"] = relationship(back_populates="findings")
