#!/usr/bin/env python3
"""Keep the docs readable on GitHub as well as in Obsidian.

Two failure modes, both silent without a check:

* `[[wikilinks]]` work in Obsidian and render as literal brackets on GitHub. GitHub is where
  people actually read this, so a wikilink is a broken link for the audience that matters.
  `.obsidian/app.json` sets Obsidian to write markdown links, but a hand-typed one bypasses it.
* A relative link that points nowhere. Docs get renamed and moved; nothing notices until a
  reader follows the link.

Scans tracked markdown only, so vendored files are out of scope by construction.
"""

import pathlib
import re
import subprocess
import sys

WIKILINK = re.compile(r"(?<!!)\[\[([^\]]+)\]\]")
MD_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


def tracked_markdown() -> list[pathlib.Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], capture_output=True, text=True, check=True
    ).stdout
    return [pathlib.Path(line) for line in out.splitlines() if line]


def main() -> int:
    problems: list[str] = []
    for path in tracked_markdown():
        text = path.read_text(encoding="utf-8")
        # Code shows wikilinks as examples — this file and docs/README.md both do. Strip
        # fenced blocks and inline spans before looking, or the documentation explaining the
        # rule trips the rule.
        prose = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        prose = re.sub(r"`[^`\n]*`", "", prose)
        for match in WIKILINK.finditer(prose):
            problems.append(f"{path}: wikilink [[{match.group(1)}]] — use [text](path.md)")
        for target in MD_LINK.findall(text):
            target = target.split()[0]  # drop any "path.md \"title\"" suffix
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = (path.parent / target.split("#")[0]).resolve()
            if not resolved.exists():
                problems.append(f"{path}: link to {target} does not exist")
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} documentation link problem(s)", file=sys.stderr)
        return 1
    print(f"checked {len(tracked_markdown())} tracked markdown files: links OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
