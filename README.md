# AI Code Review & Documentation Generator

Auto-review pull requests for **security, performance, and design** issues,
generate documentation from source, score **technical debt**, and suggest
refactors — powered by the Claude API with a zero-dependency **heuristic
fallback** so it runs even without an API key.

**Stack:** FastAPI · Claude API (Opus 4.6) · SQLAlchemy (SQLite → Postgres) ·
GitHub Webhooks + Actions.

## Features

- **PR / diff review API** — submit a full file or a unified diff, get back
  categorized findings (security / performance / design / tech-debt / style)
  with severity, line numbers, and concrete fixes.
- **Documentation generator** — reference docs, README, or tutorial style. Uses
  Claude when available; falls back to Python `ast`-based extraction.
- **Tech-debt scoring** — a transparent 0–100 score derived from findings.
- **GitHub integration** — a webhook receiver *and* a GitHub Actions workflow
  that post reviews as PR comments.
- **Graceful degradation** — no `ANTHROPIC_API_KEY`? The static-analysis engine
  still delivers a full review.

## Architecture

```
backend/app/
  main.py                 FastAPI app + lifespan (creates tables)
  config.py               env-driven settings (pydantic-settings)
  database.py  models.py  SQLAlchemy (SQLite locally, Postgres via DATABASE_URL)
  schemas.py              request/response models
  routers/                health · review · docs · webhook
  review/
    engine.py             orchestrates heuristics + LLM, merges + dedupes
    heuristics.py         regex + AST static-analysis rules (the fallback)
    docgen.py             ast-based doc generation fallback
    techdebt.py           debt scoring + refactor ranking
    prompts.py            cache-stable LLM prompts
  services/
    llm.py                Claude wrapper (structured output, streaming)
    diff_parser.py        unified-diff → changed lines w/ line numbers
    github.py             fetch PR diff, post comment, verify webhook signature
    store.py              persistence helper
  scripts/ci_review.py    GitHub Actions entrypoint
.github/workflows/code-review.yml
```

## Quick start

```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
cp .env.example .env        # optional: add ANTHROPIC_API_KEY / GITHUB_TOKEN
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for the interactive API. Run the smoke test
(no key/network needed) with `python -m tests.smoke_test`.

## API

| Method | Path                | Purpose                              |
| ------ | ------------------- | ------------------------------------ |
| GET    | `/health`           | Status + whether LLM/GitHub are wired |
| POST   | `/review`           | Review `code` or `diff`               |
| GET    | `/review`           | List past reviews                     |
| GET    | `/review/{id}`      | Full review with findings             |
| POST   | `/docs/generate`    | Generate documentation from `code`    |
| POST   | `/webhook/github`   | GitHub PR webhook (auto-review)       |

```bash
curl -X POST localhost:8000/review -H "Content-Type: application/json" -d '{
  "filename": "app.py",
  "code": "import subprocess\ndef r(c):\n    subprocess.run(c, shell=True)\n"
}'
```

## GitHub integration

**Option A — GitHub Actions (no server needed).** The workflow at
`.github/workflows/code-review.yml` runs on every PR, computes the diff, reviews
it, and comments. Add repo secret `ANTHROPIC_API_KEY` (optional). `GITHUB_TOKEN`
is provided automatically. Set `FAIL_ON: critical` in the workflow to block PRs
on serious findings.

**Option B — Webhook.** Deploy the API and point a GitHub webhook (event:
*Pull requests*) at `POST /webhook/github`. Set `GITHUB_TOKEN` and
`GITHUB_WEBHOOK_SECRET`; the server verifies the `X-Hub-Signature-256` header
and posts reviews back to the PR.

## Deploying with Postgres

Set `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/codereview` — no code
change required. Everything else runs behind `uvicorn`/`gunicorn` as usual.

## Configuration

All optional; see [`backend/.env.example`](backend/.env.example).

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./codereview.db` | Postgres for prod |
| `ANTHROPIC_API_KEY` | — | Enables Claude; omit for heuristics-only |
| `ANTHROPIC_MODEL` | `claude-opus-4-6` | |
| `GITHUB_TOKEN` | — | `pull_requests: read/write` |
| `GITHUB_WEBHOOK_SECRET` | — | Verifies webhook signatures |
