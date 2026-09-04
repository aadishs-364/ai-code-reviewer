"""CI entrypoint: review a diff and (optionally) post it as a PR comment.

Designed to run inside GitHub Actions. Reads a unified diff from a file
argument or stdin, runs the review engine (Claude if ANTHROPIC_API_KEY is set,
otherwise the local heuristics), prints a Markdown report, and posts it to the
PR when GITHUB_TOKEN / GITHUB_REPOSITORY / PR_NUMBER are present.

Exit code is non-zero when a finding at or above FAIL_ON severity is present,
so the workflow can gate a PR.

Usage:
    python -m scripts.ci_review path/to/pr.diff
    git diff origin/main...HEAD | python -m scripts.ci_review
"""

from __future__ import annotations

import os
import sys

from app.review.engine import run_review
from app.services.github import GitHubClient, render_review_markdown

_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _read_diff(argv: list[str]) -> str:
    if len(argv) > 1 and argv[1] not in ("-", ""):
        with open(argv[1], encoding="utf-8", errors="replace") as fh:
            return fh.read()
    return sys.stdin.read()


def main(argv: list[str]) -> int:
    diff = _read_diff(argv)
    if not diff.strip():
        print("No diff provided; nothing to review.")
        return 0

    result = run_review(code=None, diff=diff, filename=None, language=None)
    markdown = render_review_markdown(result)
    print(markdown)

    repo = os.getenv("GITHUB_REPOSITORY")
    pr_number = os.getenv("PR_NUMBER")
    if repo and pr_number and os.getenv("GITHUB_TOKEN"):
        try:
            GitHubClient().post_pr_comment(repo, int(pr_number), markdown)
            print(f"\nPosted review comment to {repo}#{pr_number}", file=sys.stderr)
        except Exception as exc:  # non-fatal: still surface findings in logs
            print(f"\nWarning: could not post comment: {exc}", file=sys.stderr)

    fail_on = os.getenv("FAIL_ON", "").lower()
    if fail_on in _SEVERITY_RANK:
        threshold = _SEVERITY_RANK[fail_on]
        worst = max(
            (_SEVERITY_RANK.get(f.get("severity", "info"), 0) for f in result["findings"]),
            default=-1,
        )
        if worst >= threshold:
            print(f"\nFailing: found finding at/above '{fail_on}'.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
