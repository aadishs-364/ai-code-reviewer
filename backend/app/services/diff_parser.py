"""Minimal unified-diff parser.

Extracts, per file, the lines that were *added* along with their new-file line
numbers. That lets the heuristic engine review only changed code (what a PR
reviewer cares about) and attach accurate line numbers to findings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class AddedLine:
    line_no: int  # line number in the new file
    text: str


@dataclass
class FileDiff:
    path: str
    added: list[AddedLine] = field(default_factory=list)

    @property
    def added_source(self) -> str:
        return "\n".join(a.text for a in self.added)


def parse_unified_diff(diff: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    current: FileDiff | None = None
    new_line_no = 0

    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            # "+++ b/path/to/file"  ->  "path/to/file"
            path = raw[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            current = FileDiff(path=path if path != "/dev/null" else "(deleted)")
            files.append(current)
            continue

        if raw.startswith("--- "):
            continue

        m = _HUNK_RE.match(raw)
        if m:
            new_line_no = int(m.group(1))
            continue

        if current is None:
            continue

        if raw.startswith("+"):
            current.added.append(AddedLine(line_no=new_line_no, text=raw[1:]))
            new_line_no += 1
        elif raw.startswith("-"):
            # Removed line: does not advance the new-file counter.
            continue
        else:
            # Context line.
            new_line_no += 1

    return files
