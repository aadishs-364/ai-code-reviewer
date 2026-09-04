from fastapi import APIRouter

from app.config import get_settings
from app.services.github import GitHubClient
from app.services.llm import get_llm

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "llm_enabled": get_llm().available,
        "github_configured": GitHubClient().configured,
        "model": settings.anthropic_model,
    }
