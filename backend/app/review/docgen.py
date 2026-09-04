"""Heuristic documentation generator (fallback when no LLM is available).

For Python it uses the standard `ast` module to extract real signatures and
docstrings. For other languages it falls back to a lightweight regex outline.
The output is GitHub-flavored Markdown, matching the LLM path's format.
"""

from __future__ import annotations

import ast
import re


def generate_docs(*, content: str, language: str | None, filename: str | None) -> str:
    if language == "python":
        try:
            return _python_docs(content, filename)
        except SyntaxError:
            pass  # fall through to the generic outline
    return _generic_docs(content, language, filename)


def _python_docs(source: str, filename: str | None) -> str:
    tree = ast.parse(source)
    title = filename or "module"
    out: list[str] = [f"# `{title}`", ""]

    module_doc = ast.get_docstring(tree)
    if module_doc:
        out += [module_doc, ""]

    functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]

    if functions:
        out += ["## Functions", ""]
        for fn in functions:
            out += _fn_section(fn, level=3)

    if classes:
        out += ["## Classes", ""]
        for cls in classes:
            out.append(f"### `class {cls.name}`")
            cdoc = ast.get_docstring(cls)
            if cdoc:
                out += ["", cdoc]
            methods = [
                n for n in cls.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            out.append("")
            for m in methods:
                out += _fn_section(m, level=4)

    return "\n".join(out).rstrip() + "\n"


def _fn_section(fn: ast.FunctionDef | ast.AsyncFunctionDef, level: int) -> list[str]:
    prefix = "async def " if isinstance(fn, ast.AsyncFunctionDef) else "def "
    try:
        args = ast.unparse(fn.args)
    except Exception:
        args = ", ".join(a.arg for a in fn.args.args)
    heading = "#" * level
    lines = [f"{heading} `{prefix}{fn.name}({args})`"]
    doc = ast.get_docstring(fn)
    if doc:
        lines += ["", doc]
    else:
        lines += ["", "_No docstring._"]
    lines.append("")
    return lines


def _generic_docs(content: str, language: str | None, filename: str | None) -> str:
    title = filename or (language or "source")
    out = [f"# `{title}`", ""]
    patterns = [
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\([^)]*\)",
        r"^\s*(?:public|private|protected)?\s*class\s+(\w+)",
        r"^\s*func\s+(\w+)\s*\(",
    ]
    names: list[str] = []
    for line in content.splitlines():
        for pat in patterns:
            m = re.match(pat, line)
            if m:
                names.append(m.group(0).strip())
    if names:
        out += ["## Declarations", ""]
        out += [f"- `{n}`" for n in names]
    else:
        out += ["_No top-level declarations detected._"]
    return "\n".join(out) + "\n"
