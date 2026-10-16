"""Publish configs/glossary.yaml where it is read: the dashboard bundle and the docs.

Writes web/src/lib/glossary.json (the dashboard is built from web/ alone, so it cannot read
configs/ at build time) and docs/glossary.md (the same terms as a page). Both are committed, and
tests/unit/test_glossary.py fails when either no longer matches the YAML — run `make glossary`
after editing the glossary.
"""

import json
import sys
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "configs" / "glossary.yaml"
TARGET = ROOT / "web" / "src" / "lib" / "glossary.json"
PAGE = ROOT / "docs" / "glossary.md"


def _terms() -> dict[str, dict[str, str]]:
    terms: dict[str, dict[str, str]] = yaml.safe_load(SOURCE.read_text())["terms"]
    return terms


def render() -> str:
    return json.dumps(_terms(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def render_page() -> str:
    """The glossary as a page, alphabetical by plain name, one entry per term."""
    lines = [
        "# Glossary",
        "",
        "Every term the dashboard shows and the API returns, in plain words. Generated from",
        "[configs/glossary.yaml](../configs/glossary.yaml) by `make glossary` — edit that file,",
        "not this one. The dashboard shows the same text when you hover a label.",
        "",
    ]
    entries = sorted(_terms().items(), key=lambda kv: kv[1]["label"].lower())

    def heading_of(entry: dict[str, str]) -> str:
        return entry["label"] + (f" — {entry['term']}" if entry.get("term") else "")

    seen = [heading_of(entry) for _, entry in entries]
    for key, entry in entries:
        heading = heading_of(entry)
        if seen.count(heading) > 1:  # two fields that read the same: name the field
            heading += f" (`{key}`)"
        lines += [f"## {heading}", "", textwrap.fill(f"`{key}` · {entry['meaning']}", 100)]
        if entry.get("read"):
            lines += ["", textwrap.fill(f"**How to read it:** {entry['read']}", 100)]
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    TARGET.write_text(render())
    PAGE.write_text(render_page())
    print(f"wrote {TARGET.relative_to(ROOT)} and {PAGE.relative_to(ROOT)}", file=sys.stderr)
