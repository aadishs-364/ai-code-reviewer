"""GitHub REST integration: fetch PR diffs and post review comments.

Uses a personal access token (or GitHub App installation token) via
GITHUB_TOKEN. Webhook signatures are verified with GITHUB_WEBHOOK_SECRET.
"""

from __future__ import annotations

import hashlib
import hmac

import httpx

from app.config import get_settings


class GitHubClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _headers(self, accept: str = "application/vnd.github+json") -> dict:
        headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"
        return headers

    @property
    def configured(self) -> bool:
        return bool(self.settings.github_token)

    def get_pr_diff(self, repo: str, pr_number: int) -> str:
        """Return the unified diff for a pull request. `repo` is 'owner/name'."""
        url = f"{self.settings.github_api_url}/repos/{repo}/pulls/{pr_number}"
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=self._headers("application/vnd.github.v3.diff"))
            resp.raise_for_status()
            return resp.text

    def post_pr_comment(self, repo: str, pr_number: int, body: str) -> None:
        """Post a general comment on the PR conversation."""
        url = f"{self.settings.github_api_url}/repos/{repo}/issues/{pr_number}/comments"
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=self._headers(), json={"body": body})
            resp.raise_for_status()


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """Verify a GitHub webhook 'X-Hub-Signature-256' header."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


def render_review_markdown(result: dict) -> str:
    """Format a review result dict as a Markdown PR comment."""
    engine = result.get("engine", "heuristic")
    score = result.get("tech_debt_score")
    lines = ["## 🤖 AI Code Review", ""]
    if result.get("summary"):
        lines += [result["summary"], ""]
    lines.append(f"**Engine:** {engine} &nbsp;|&nbsp; **Tech-debt score:** {score}/100")
    lines.append("")

    findings = result.get("findings", [])
    if not findings:
        lines.append("No issues found. ✅")
        return "\n".join(lines)

    icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}
    lines += ["| Sev | Category | Location | Issue |", "| --- | --- | --- | --- |"]
    for f in findings:
        icon = icons.get(f.get("severity", "info"), "⚪")
        loc = ""
        if f.get("file_path"):
            loc += f.get("file_path")
        if f.get("line"):
            loc += f":{f['line']}"
        title = f.get("title", "").replace("|", "\\|")
        lines.append(
            f"| {icon} {f.get('severity')} | {f.get('category')} | {loc or '—'} | {title} |"
        )
    return "\n".join(lines)
