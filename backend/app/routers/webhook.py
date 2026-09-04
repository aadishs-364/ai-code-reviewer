import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.config import get_settings
from app.database import SessionLocal
from app.review.engine import run_review
from app.services.github import GitHubClient, render_review_markdown, verify_signature
from app.services.store import persist_review

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])

_REVIEWABLE_ACTIONS = {"opened", "reopened", "synchronize", "ready_for_review"}


def _process_pull_request(repo: str, pr_number: int, commit_sha: str | None) -> None:
    """Background worker: fetch the PR diff, review it, persist, and comment."""
    gh = GitHubClient()
    db = SessionLocal()
    try:
        diff = gh.get_pr_diff(repo, pr_number)
        result = run_review(code=None, diff=diff, filename=None, language=None)
        persist_review(
            db, result, source="github_pr",
            repo=repo, pr_number=pr_number, commit_sha=commit_sha,
        )
        gh.post_pr_comment(repo, pr_number, render_review_markdown(result))
        logger.info("Reviewed %s#%s (%d findings)", repo, pr_number, len(result["findings"]))
    except Exception:
        logger.exception("Failed to review %s#%s", repo, pr_number)
    finally:
        db.close()


@router.post("/github")
async def github_webhook(
    request: Request,
    background: BackgroundTasks,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
) -> dict:
    settings = get_settings()
    body = await request.body()

    if settings.github_webhook_secret:
        if not verify_signature(settings.github_webhook_secret, body, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event == "ping":
        return {"status": "pong"}

    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event}

    payload = await request.json()
    action = payload.get("action")
    if action not in _REVIEWABLE_ACTIONS:
        return {"status": "ignored", "action": action}

    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {}).get("full_name")
    pr_number = pr.get("number")
    commit_sha = pr.get("head", {}).get("sha")
    if not repo or pr_number is None:
        raise HTTPException(status_code=422, detail="Missing repository or PR number")

    background.add_task(_process_pull_request, repo, pr_number, commit_sha)
    return {"status": "accepted", "repo": repo, "pr": pr_number}
