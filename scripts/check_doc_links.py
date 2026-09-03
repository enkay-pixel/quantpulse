#!/usr/bin/env python3
"""Keep the docs readable on GitHub as well as in Obsidian.

Two failure modes, both silent without a check:

* `[[wikilinks]]` work in Obsidian and render as literal brackets on GitHub. GitHub is where
  people actually read this, so a wikilink is a broken link for the audience that matters.
  `.obsidian/app.json` sets Obsidian to write markdown links, but a hand-typed one bypasses it.
* A relative link that points nowhere. Docs get renamed and moved; nothing notices until a
  reader follows the link.
* A link to a heading that is no longer there. Headings get reworded far more often than files
  get renamed, and an anchor that misses does not fail loudly — GitHub simply leaves the reader
  at the top of the page, which reads as though the link worked.

Scans tracked markdown only, so vendored files are out of scope by construction.
"""

import pathlib
import re
import subprocess
import sys

WIKILINK = re.compile(r"(?<!!)\[\[([^\]]+)\]\]")
MD_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*$", re.MULTILINE)


def slugify(heading: str) -> str:
    """Reduce heading text to the id GitHub gives it.

    Inline markup is dropped rather than transliterated, because GitHub slugs the rendered
    text: `` `code` `` contributes its contents and a link contributes its label, not its URL.
    Underscores survive, since a heading is far more likely to name an identifier than to use
    underscore emphasis.
    """
    text = re.sub(r"`([^`]*)`", r"\1", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Only asterisk emphasis is stripped. GitHub slugs the *rendered* heading, where an
    # underscore inside a word is literal text rather than markup, so removing them here
    # would miss `vol_63` and report a working link as broken.
    text = re.sub(r"[*~]", "", text)
    text = re.sub(r"[^\w\s-]", "", text.strip().lower())
    # Each space becomes its own hyphen rather than collapsing runs: dropping the punctuation
    # from "changes — and" leaves two spaces, and GitHub renders that as a double hyphen.
    return re.sub(r"\s", "-", text)


def anchors(text: str) -> set[str]:
    """Every id a reader can link to in one file.

    Repeated headings take a numeric suffix in order of appearance, the way GitHub
    disambiguates them, so the second "Related" is `related-1`.
    """
    body = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    seen: dict[str, int] = {}
    found: set[str] = set()
    for heading in HEADING.findall(body):
        slug = slugify(heading)
        if not slug:
            continue
        count = seen.get(slug, 0)
        found.add(slug if count == 0 else f"{slug}-{count}")
        seen[slug] = count + 1
    return found


def tracked_markdown() -> list[pathlib.Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], capture_output=True, text=True, check=True
    ).stdout
    return [pathlib.Path(line) for line in out.splitlines() if line]


def main() -> int:
    cache: dict[pathlib.Path, set[str]] = {}

    def anchors_for(target: pathlib.Path) -> set[str]:
        if target not in cache:
            cache[target] = anchors(target.read_text(encoding="utf-8"))
        return cache[target]

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
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            relative, _, fragment = target.partition("#")
            # A bare "#anchor" points at the file it is written in.
            resolved = (path.parent / relative).resolve() if relative else path.resolve()
            if not resolved.exists():
                problems.append(f"{path}: link to {target} does not exist")
                continue
            if not fragment or resolved.suffix != ".md":
                continue
            if fragment not in anchors_for(resolved):
                where = relative or "this file"
                problems.append(f"{path}: link to {target} — no heading '#{fragment}' in {where}")
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} documentation link problem(s)", file=sys.stderr)
        return 1
    print(f"checked {len(tracked_markdown())} tracked markdown files: links OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
