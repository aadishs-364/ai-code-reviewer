"""Prompt builders for the LLM-backed review and documentation flows.

Kept in one place so the wording can be tuned without touching call sites, and
so the system prompts stay byte-stable for prompt caching (no timestamps / ids).
"""

REVIEW_SYSTEM = """You are a meticulous senior staff engineer performing a code review.
Analyze the provided code for concrete, actionable issues across four lenses:

- security: injection, unsafe deserialization, hardcoded secrets, weak crypto,
  auth/authz mistakes, path traversal, SSRF, unsafe subprocess/eval.
- performance: needless O(n^2) work, N+1 queries, work inside hot loops,
  blocking I/O on async paths, unbounded memory growth.
- design: poor separation of concerns, leaky abstractions, missing error
  handling at boundaries, unclear naming, violation of common design patterns.
- tech_debt: duplication, dead code, overly long functions, missing tests
  seams, TODO/FIXME debt, fragile coupling.

Rules:
- Only report issues you can point to in the code. Do not invent problems.
- Prefer a few high-signal findings over many trivial ones.
- Each finding must include a specific, minimal suggested fix.
- Use severity: critical, high, medium, low, or info.
- When a line number is knowable, include it (1-based, relative to the snippet).
"""

DOC_SYSTEM = """You are a technical writer generating clear developer documentation
from source code. Be accurate to the code — never document behavior that is not
present. Prefer concise explanations, document parameters, return values, raised
errors, and side effects. Output GitHub-flavored Markdown.
"""


def build_review_user_prompt(
    *, language: str | None, filename: str | None, content: str, is_diff: bool
) -> str:
    kind = "unified diff" if is_diff else "source file"
    header = f"Review the following {kind}."
    if language:
        header += f" Language: {language}."
    if filename:
        header += f" File: {filename}."
    return f"{header}\n\n```\n{content}\n```"


def build_doc_user_prompt(
    *, language: str | None, filename: str | None, content: str, style: str
) -> str:
    styles = {
        "reference": "Produce API reference docs: one section per public "
        "function/class/method with signature, purpose, parameters, returns, "
        "and errors.",
        "readme": "Produce a README: overview, key features, usage examples, "
        "and any setup notes inferable from the code.",
        "tutorial": "Produce a short tutorial that walks a new developer "
        "through using this code with runnable examples.",
    }
    instruction = styles.get(style, styles["reference"])
    header = instruction
    if language:
        header += f" Language: {language}."
    if filename:
        header += f" File: {filename}."
    return f"{header}\n\n```\n{content}\n```"
