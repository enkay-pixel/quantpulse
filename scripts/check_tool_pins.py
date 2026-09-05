#!/usr/bin/env python3
"""Keep every tool version that is written down twice from drifting apart.

Four tools are pinned in two places each: a `rev` in `.pre-commit-config.yaml` decides what
runs on a commit, and a second declaration decides what runs in CI — `ruff` from the
`pyproject.toml` pin, and `uv`, `markdownlint` and `gitleaks` from the workflow. When the two
disagree the failure is not a missing tool but a disagreeing one: the hook formats a file one
way, CI checks it another, and the commit that passed locally is rejected.

Nothing keeps them together on its own. A dependency bot moves the `pyproject.toml` pin and
has no idea the hook exists, so the pair drifts on every release of the one tool pinned that
way, and each drift costs a diagnosis before it costs a one-line edit.

The pre-commit `rev` is always the mirror here, so `--fix` rewrites it from whichever file
declares the version. Checking and fixing read the same table, which is the point: four
separate shell blocks doing this by hand could each break in their own way, and one of them
already nearly did by matching the wrong `version:` line in the workflow.
"""

import argparse
import pathlib
import re
import sys
from dataclasses import dataclass

CONFIG = pathlib.Path(".pre-commit-config.yaml")
WORKFLOW = pathlib.Path(".github/workflows/ci.yml")


@dataclass(frozen=True)
class Pin:
    """One tool, its pre-commit repo, and where its version is declared for CI."""

    name: str
    repo: str
    source: pathlib.Path
    pattern: str
    #: Prepended to the declared version to form the rev, where the two differ by a "v".
    prefix: str = ""


PINS = (
    Pin(
        "ruff",
        "https://github.com/astral-sh/ruff-pre-commit",
        pathlib.Path("pyproject.toml"),
        r'"ruff==([0-9][^"]*)"',
        prefix="v",
    ),
    # Anchored on the setup-uv block: the first `version:` in the workflow belongs to whatever
    # action happens to be pinned first, and matching that would compare the wrong thing.
    Pin(
        "uv",
        "https://github.com/astral-sh/uv-pre-commit",
        WORKFLOW,
        r'astral-sh/setup-uv(?:.|\n){0,400}?version: "([^"]+)"',
    ),
    Pin(
        "markdownlint",
        "https://github.com/DavidAnson/markdownlint-cli2",
        WORKFLOW,
        r"MARKDOWNLINT_VERSION: *(\S+)",
    ),
    Pin("gitleaks", "https://github.com/gitleaks/gitleaks", WORKFLOW, r"GITLEAKS_VERSION: *(\S+)"),
)


def hook_rev(text: str, repo: str) -> str | None:
    match = re.search(rf"- +repo: +{re.escape(repo)} *\n +rev: *(\S+)", text)
    return match.group(1) if match else None


def set_hook_rev(text: str, repo: str, rev: str) -> str:
    return re.sub(rf"(- +repo: +{re.escape(repo)} *\n +rev: *)\S+", rf"\g<1>{rev}", text, count=1)


def declared(pin: Pin) -> str | None:
    match = re.search(pin.pattern, pin.source.read_text(encoding="utf-8"))
    return pin.prefix + match.group(1) if match else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix", action="store_true", help="rewrite the pre-commit rev to match the source"
    )
    args = parser.parse_args()

    text = CONFIG.read_text(encoding="utf-8")
    problems: list[str] = []
    fixed: list[str] = []

    for pin in PINS:
        want = declared(pin)
        have = hook_rev(text, pin.repo)
        if want is None:
            problems.append(f"{pin.name}: no version found in {pin.source}")
            continue
        if have is None:
            problems.append(f"{pin.name}: no rev found for {pin.repo} in {CONFIG}")
            continue
        if want == have:
            continue
        if args.fix:
            text = set_hook_rev(text, pin.repo, want)
            fixed.append(f"{pin.name}: {have} -> {want}")
        else:
            problems.append(
                f"{pin.name} drift: {CONFIG}={have} {pin.source}={want} "
                f"— run scripts/check_tool_pins.py --fix"
            )

    if fixed:
        CONFIG.write_text(text, encoding="utf-8")
        for line in fixed:
            print(f"updated {line}")
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} tool pin problem(s)", file=sys.stderr)
        return 1
    if not fixed:
        print(f"checked {len(PINS)} tool pins: all agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
