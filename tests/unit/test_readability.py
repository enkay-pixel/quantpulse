"""The dashboard and the API read without a guide, and a change cannot quietly undo that.

Every column header and stat label goes through the glossary, so it shows a plain name, the
technical term small beneath it, and what it means on hover. Every endpoint says what it returns.
(Every panel's one-line explanation is enforced by the compiler instead: `explain` is a required
prop of Section.)
"""

import re
from pathlib import Path

import yaml

from quantpulse.api.app import create_app

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web" / "src"
TERMS = set(yaml.safe_load((ROOT / "configs/glossary.yaml").read_text())["terms"])


def _sources() -> dict[str, str]:
    return {
        str(p.relative_to(WEB)): p.read_text()
        for p in WEB.rglob("*.tsx")
        if "test" not in p.relative_to(WEB).parts
    }


def test_every_column_header_is_a_glossary_term() -> None:
    sources = _sources()
    headers = [
        (name, m.group(1).strip())
        for name, src in sources.items()
        for m in re.finditer(r"<th\b[^>]*>(.*?)</th>", src, re.S)
    ]
    assert len(headers) >= 40, f"found {len(headers)} headers — the pattern is reading nothing"
    raw = [f"{name}: {text[:40]!r}" for name, text in headers if "<Term" not in text]
    assert not raw, f"column headers in raw text — use <Term id=...>: {raw}"


def test_every_term_the_dashboard_uses_has_an_entry() -> None:
    ids = {
        m.group(1) for src in _sources().values() for m in re.finditer(r'<Term\s+id="([^"]+)"', src)
    }
    assert len(ids) >= 40, f"found {len(ids)} terms — the pattern is reading nothing"
    assert not ids - TERMS, f"add to configs/glossary.yaml: {sorted(ids - TERMS)}"


def _owning_tag(src: str, at: int) -> str:
    """The name of the JSX tag an attribute at `at` belongs to: the last `<Name` before it."""
    opened = src.rfind("<", 0, at)
    return src[opened + 1 :].split(None, 1)[0].rstrip("/>")


def test_card_labels_go_through_the_glossary() -> None:
    """A stat card labelled in raw text ("Max DD") is the same gap as a raw column header. A
    `label` override on a Term itself is fine: the glossary still supplies its meaning."""
    raw = [
        f"{name}: {m.group(1)!r}"
        for name, src in _sources().items()
        for m in re.finditer(r'\blabel="([^"]*)"', src)
        if _owning_tag(src, m.start()) in {"StatCard", "Metric", "Stat"}
    ]
    assert not raw, f"card labels in raw text — use label={{<Term id=... />}}: {raw}"


def test_every_endpoint_says_what_it_returns() -> None:
    spec = create_app().openapi()
    missing = [
        f"{method.upper()} {path}"
        for path, ops in spec["paths"].items()
        for method, op in ops.items()
        if not op.get("description")
    ]
    assert not missing, f"add a one-line docstring to: {missing}"


def test_docs_open_with_a_plain_summary() -> None:
    """Every ADR, every finding and the reference pages open with a plain "In short" line, so a
    reader learns what a page says before its detail — and a new page cannot skip it."""
    docs = ROOT / "docs"
    pages = [
        *sorted((docs / "adr").glob("[0-9]*.md")),
        *sorted(p for p in (docs / "findings").glob("*.md") if p.name != "README.md"),
        docs / "architecture.md",
        docs / "runbook.md",
        docs / "data-dictionary.md",
    ]
    assert len(pages) >= 25, f"found {len(pages)} pages — the globs are reading nothing"
    missing = [
        str(p.relative_to(ROOT))
        for p in pages
        if "**In short:**" not in "\n".join(p.read_text().splitlines()[:8])
    ]
    assert not missing, f"open these with an **In short:** line in plain words: {missing}"
