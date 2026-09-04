"""Local static-analysis engine.

This runs with zero external dependencies and no API key. It powers the
fallback reviewer and always runs alongside the LLM so every review has a
deterministic baseline. Rules are intentionally high-precision (few false
positives) rather than exhaustive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LANGUAGE_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".sql": "sql",
}


@dataclass
class Rule:
    category: str
    severity: str
    pattern: re.Pattern
    title: str
    detail: str
    suggestion: str
    languages: tuple[str, ...] | None = None  # None => applies to all


def _c(pattern: str) -> re.Pattern:
    return re.compile(pattern)


# Per-line regex rules. Kept high-signal on purpose.
RULES: list[Rule] = [
    # ---- Security --------------------------------------------------------
    Rule(
        "security", "critical",
        _c(r"\b(eval|exec)\s*\("),
        "Use of eval/exec",
        "Dynamic code execution can lead to arbitrary code execution if any "
        "input is attacker-influenced.",
        "Replace with an explicit parser, a dispatch dict, or ast.literal_eval.",
        ("python",),
    ),
    Rule(
        "security", "high",
        _c(r"subprocess\.(run|call|Popen|check_output)\([^)]*shell\s*=\s*True"),
        "subprocess with shell=True",
        "Running a shell with interpolated arguments enables command injection.",
        "Pass an argument list and drop shell=True, or shlex.quote inputs.",
        ("python",),
    ),
    Rule(
        "security", "high",
        _c(r"\bos\.system\s*\("),
        "os.system call",
        "os.system runs a shell and is prone to command injection.",
        "Use subprocess.run([...]) with an argument list instead.",
        ("python",),
    ),
    Rule(
        "security", "high",
        _c(r"\bpickle\.loads?\s*\("),
        "Unsafe pickle deserialization",
        "Unpickling untrusted data can execute arbitrary code.",
        "Use json or another safe format for untrusted input.",
        ("python",),
    ),
    Rule(
        "security", "medium",
        _c(r"\byaml\.load\s*\((?![^)]*Loader)"),
        "yaml.load without a safe Loader",
        "yaml.load can instantiate arbitrary Python objects.",
        "Use yaml.safe_load(...) instead.",
        ("python",),
    ),
    Rule(
        "security", "high",
        _c(r"""(?i)(password|passwd|secret|api[_-]?key|token|access[_-]?key)\s*=\s*['"][^'"]{6,}['"]"""),
        "Possible hardcoded secret",
        "A credential appears to be hardcoded in source.",
        "Load secrets from environment variables or a secret manager.",
        None,
    ),
    Rule(
        "security", "critical",
        _c(r"AKIA[0-9A-Z]{16}"),
        "Hardcoded AWS access key ID",
        "An AWS access key ID pattern is present in the code.",
        "Remove it, rotate the key immediately, and load from the environment.",
        None,
    ),
    Rule(
        "security", "medium",
        _c(r"\bhashlib\.(md5|sha1)\s*\("),
        "Weak hash function",
        "MD5/SHA1 are unsuitable for security-sensitive hashing.",
        "Use SHA-256+; for passwords use bcrypt/argon2/scrypt.",
        ("python",),
    ),
    Rule(
        "security", "medium",
        _c(r"verify\s*=\s*False"),
        "TLS verification disabled",
        "Disabling certificate verification exposes traffic to MITM attacks.",
        "Remove verify=False; fix the underlying certificate trust issue.",
        None,
    ),
    Rule(
        "security", "high",
        _c(r"""(execute|executemany|cursor\.execute)\s*\(\s*(f['"]|['"].*%\s|['"].*['"]\s*\+)"""),
        "Possible SQL injection",
        "SQL built with string formatting/concatenation is injectable.",
        "Use parameterized queries (placeholders + params), never string building.",
        None,
    ),
    Rule(
        "security", "medium",
        _c(r"\.innerHTML\s*="),
        "Assignment to innerHTML",
        "Writing raw HTML can introduce DOM-based XSS.",
        "Use textContent, or sanitize with a vetted library before injecting HTML.",
        ("javascript", "typescript"),
    ),
    Rule(
        "security", "high",
        _c(r"child_process\.(exec|execSync)\s*\("),
        "child_process.exec",
        "exec spawns a shell and is prone to command injection.",
        "Use execFile/spawn with an argument array instead.",
        ("javascript", "typescript"),
    ),
    Rule(
        "security", "medium",
        _c(r"\bdebug\s*=\s*True"),
        "Debug mode enabled",
        "Debug mode can leak stack traces and enable interactive consoles.",
        "Ensure debug is disabled in production (drive it from config/env).",
        ("python",),
    ),
    # ---- Performance -----------------------------------------------------
    Rule(
        "performance", "low",
        _c(r"SELECT\s+\*", ),
        "SELECT * query",
        "Selecting all columns fetches more data than needed and is fragile.",
        "Select only the columns you use.",
        None,
    ),
    Rule(
        "performance", "medium",
        _c(r"\.iterrows\s*\("),
        "DataFrame.iterrows in a hot path",
        "iterrows is very slow for large frames.",
        "Vectorize with pandas/numpy operations or use itertuples.",
        ("python",),
    ),
    Rule(
        "performance", "low",
        _c(r"\btime\.sleep\s*\("),
        "Blocking sleep",
        "time.sleep blocks the thread/event loop.",
        "In async code use asyncio.sleep; avoid fixed sleeps for coordination.",
        ("python",),
    ),
    # ---- Design / correctness -------------------------------------------
    Rule(
        "design", "medium",
        _c(r"except\s*:\s*$"),
        "Bare except",
        "A bare except swallows all exceptions, including KeyboardInterrupt.",
        "Catch specific exception types.",
        ("python",),
    ),
    Rule(
        "design", "low",
        _c(r"except[^:]*:\s*pass\s*$"),
        "Silently swallowed exception",
        "except ...: pass hides errors and complicates debugging.",
        "Log the error or handle it explicitly.",
        ("python",),
    ),
    Rule(
        "design", "low",
        _c(r"def\s+\w+\([^)]*=\s*(\[\]|\{\})"),
        "Mutable default argument",
        "Mutable defaults are shared across calls and cause subtle bugs.",
        "Default to None and create the container inside the function.",
        ("python",),
    ),
    Rule(
        "style", "info",
        _c(r"[!=]=\s*None\b"),
        "Comparison to None with ==/!=",
        "Identity comparison is clearer and correct for None.",
        "Use 'is None' / 'is not None'.",
        ("python",),
    ),
    Rule(
        "design", "low",
        _c(r"console\.log\s*\("),
        "Leftover console.log",
        "Debug logging left in code clutters output.",
        "Remove it or route through a proper logger.",
        ("javascript", "typescript"),
    ),
    # ---- Tech debt -------------------------------------------------------
    Rule(
        "tech_debt", "info",
        _c(r"\b(TODO|FIXME|XXX|HACK)\b"),
        "Tracked tech-debt marker",
        "A TODO/FIXME/HACK marker indicates deferred work.",
        "Convert to a tracked issue with an owner, or resolve it.",
        None,
    ),
]


def _in_comment_or_string_noise(line: str) -> bool:
    # Cheap guard: skip pure comment lines for secret/SQL style rules is risky,
    # so we keep them. This hook is a placeholder for future refinement.
    return False


def scan_lines(
    lines: list[tuple[int, str]], language: str | None
) -> list[dict]:
    """Apply per-line regex rules. `lines` is a list of (line_no, text)."""
    findings: list[dict] = []
    for line_no, text in lines:
        for rule in RULES:
            if rule.languages and language not in rule.languages:
                continue
            if rule.pattern.search(text):
                findings.append(
                    {
                        "category": rule.category,
                        "severity": rule.severity,
                        "title": rule.title,
                        "detail": rule.detail,
                        "suggestion": rule.suggestion,
                        "line": line_no,
                        "origin": "heuristic",
                    }
                )
    return findings


def scan_python_blocks(source: str) -> list[dict]:
    """Whole-file Python checks that need block context (long functions).

    Only run on full files, not fragmentary diffs.
    """
    findings: list[dict] = []
    lines = source.splitlines()
    func_start: int | None = None
    func_name = ""
    func_indent = 0

    def close_function(end_idx: int) -> None:
        nonlocal func_start
        if func_start is None:
            return
        length = end_idx - func_start
        if length > 50:
            findings.append(
                {
                    "category": "tech_debt",
                    "severity": "medium",
                    "title": f"Long function '{func_name}' ({length} lines)",
                    "detail": "Long functions are harder to test and reason about.",
                    "suggestion": "Extract cohesive steps into smaller helpers.",
                    "line": func_start + 1,
                    "origin": "heuristic",
                }
            )
        func_start = None

    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped:
            continue
        indent = len(raw) - len(raw.lstrip())
        m = re.match(r"def\s+(\w+)\s*\(", stripped)
        if m:
            # A def at same/less indent closes the previous function.
            if func_start is not None and indent <= func_indent:
                close_function(i)
            func_start = i
            func_name = m.group(1)
            func_indent = indent
        elif func_start is not None and indent <= func_indent and not stripped.startswith(")"):
            close_function(i)

    close_function(len(lines))
    return findings
