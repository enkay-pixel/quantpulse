"""The findings index, read from the table in `docs/findings/README.md`.

That table is the single place each investigation is summarised — its question and what came
back — and the dashboard shows it rather than a second copy that would drift from it. Outcomes
are written in markdown for the page; here they are reduced to plain text.
"""

import re
from dataclasses import dataclass
from pathlib import Path

_ROW = re.compile(
    r"^\| \[(?P<title>[^\]]+)\]\((?P<file>[^)\s]+)\) \| (?P<question>.+?) \| (?P<outcome>.+) \|$"
)
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")


@dataclass(frozen=True)
class Finding:
    title: str
    url: str
    question: str
    outcome: str


def plain(markdown: str) -> str:
    """Markdown inline formatting reduced to its text: links to their words, emphasis and code
    marks dropped, strike-through markers removed."""
    text = _LINK.sub(r"\1", markdown)
    for mark in ("**", "~~", "`"):
        text = text.replace(mark, "")
    return re.sub(r"(?<!\w)\*(?!\s)|(?<!\s)\*(?!\w)", "", text).strip()


def parse(index: str, base_url: str) -> list[Finding]:
    """One Finding per row of the index table, in the table's order."""
    findings = []
    for line in index.splitlines():
        m = _ROW.match(line.strip())
        if not m:
            continue
        findings.append(
            Finding(
                title=plain(m["title"]),
                url=f"{base_url.rstrip('/')}/{m['file']}",
                question=plain(m["question"]),
                outcome=plain(m["outcome"]),
            )
        )
    return findings


def load(path: Path, base_url: str) -> list[Finding]:
    return parse(path.read_text(), base_url) if path.exists() else []
