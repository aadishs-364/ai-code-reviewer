"""Lightweight smoke test — no API key or network needed.

Run: python -m tests.smoke_test
Exercises the heuristic engine, diff parser, doc generator, tech-debt scoring,
and the FastAPI HTTP surface end to end.
"""

from __future__ import annotations

import os
import tempfile

# Use an isolated temp DB so the test never touches a real one.
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(
    tempfile.gettempdir(), "codereview_smoke.db"
)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.review.engine import run_review  # noqa: E402
from app.services.diff_parser import parse_unified_diff  # noqa: E402

VULN_CODE = '''\
import subprocess, hashlib, pickle

API_KEY = "supersecret_hardcoded_value"

def run(cmd):
    subprocess.run(cmd, shell=True)          # command injection
    return hashlib.md5(cmd.encode())         # weak hash

def load(data):
    return pickle.loads(data)                # unsafe deserialization

def check(x):
    if x == None:                            # style: == None
        return
    try:
        risky()
    except:                                  # bare except
        pass
# TODO: refactor this module
'''

SAMPLE_DIFF = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,4 @@
 import os
+password = "hunter2000"
+eval(user_input)
 print("ok")
"""


def check(cond: bool, msg: str) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {msg}")
    if not cond:
        raise SystemExit(1)


def main() -> None:
    # 1. Heuristic review of a full file
    result = run_review(code=VULN_CODE, diff=None, filename="vuln.py", language=None)
    cats = {f["category"] for f in result["findings"]}
    titles = {f["title"] for f in result["findings"]}
    check(result["engine"] == "heuristic", "runs without API key via heuristics")
    check("security" in cats, "detects security findings")
    check(any("hardcoded" in t.lower() for t in titles), "flags hardcoded secret")
    check(any("shell=True" in t for t in titles), "flags subprocess shell=True")
    check(0 < result["tech_debt_score"] <= 100, "computes tech-debt score")

    # 2. Diff parsing + review with real line numbers
    parsed = parse_unified_diff(SAMPLE_DIFF)
    check(parsed[0].path == "app.py", "diff parser extracts file path")
    diff_result = run_review(code=None, diff=SAMPLE_DIFF, filename=None, language=None)
    check(
        any(f.get("file_path") == "app.py" and f.get("line") for f in diff_result["findings"]),
        "diff findings carry file path + line",
    )

    # 3. Doc generation (heuristic AST path)
    docs = run_review  # placeholder to keep flake quiet
    from app.review.engine import run_docs

    doc = run_docs(code=VULN_CODE, filename="vuln.py", language=None, style="reference")
    check(doc["engine"] == "heuristic", "docs fall back to heuristic AST")
    check("run" in doc["documentation"], "docs list functions")

    # 4. HTTP surface (context manager runs lifespan -> creates tables)
    with TestClient(app) as client:
        r = client.get("/health")
        check(r.status_code == 200 and r.json()["status"] == "ok", "GET /health ok")

        r = client.post("/review", json={"code": VULN_CODE, "filename": "vuln.py"})
        check(r.status_code == 200, "POST /review ok")
        review_id = r.json()["id"]
        check(len(r.json()["findings"]) > 0, "review returns findings")

        r = client.get(f"/review/{review_id}")
        check(r.status_code == 200, "GET /review/{id} ok")

        r = client.get("/review")
        check(r.status_code == 200 and len(r.json()) >= 1, "GET /review lists reviews")

        r = client.post("/docs/generate", json={"code": VULN_CODE, "filename": "vuln.py"})
        check(r.status_code == 200 and r.json()["documentation"], "POST /docs/generate ok")

        r = client.post("/webhook/github", json={}, headers={"X-GitHub-Event": "ping"})
        check(r.status_code == 200 and r.json()["status"] == "pong", "webhook ping ok")

    print("\nAll smoke checks passed.")


if __name__ == "__main__":
    main()
