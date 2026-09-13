#!/usr/bin/env python3
"""Keep every tool version that is written down twice from drifting apart.

Five tools are pinned in two places each. Four are a pre-commit `rev` against the version CI
installs — `ruff` from the `pyproject.toml` pin, and `uv`, `markdownlint` and `gitleaks` from
the workflow. The fifth is the MLflow server image against the client in the lock: the
registry is a client/server pair, and the image comment asks for them to match.

When a pair disagrees the failure is not a missing tool but a disagreeing one: the hook
formats a file one way and CI checks it another, or a client talks to a server built from a
different release. Nothing keeps a pair together on its own — a dependency bot moves the side
it knows about and has no idea the other exists — so every release of a tool pinned this way
drifts it, and each drift costs a diagnosis before it costs a one-line edit.

One side of each pair is the mirror, so `--fix` rewrites it from whichever file declares the
version. Checking and fixing read the same table, which is the point: separate shell blocks
doing this by hand could each break in their own way, and one already nearly did by matching
the wrong `version:` line in the workflow.
"""

import argparse
import pathlib
import re
import sys
from collections import defaultdict
from dataclasses import dataclass

CONFIG = pathlib.Path(".pre-commit-config.yaml")
WORKFLOW = pathlib.Path(".github/workflows/ci.yml")
PYPROJECT = pathlib.Path("pyproject.toml")
LOCK = pathlib.Path("uv.lock")


def pre_commit_rev(repo: str) -> str:
    """Pattern matching the `rev:` belonging to one pre-commit repo, not the next one down."""
    return rf"- +repo: +{re.escape(repo)} *\n +rev: *(\S+)"


@dataclass(frozen=True)
class Pin:
    """A version declared in one file and repeated in another."""

    name: str
    source: pathlib.Path
    source_pattern: str
    mirror: pathlib.Path
    mirror_pattern: str
    #: Prepended to the declared version to form the mirrored value, where the two differ.
    prefix: str = ""


PINS = (
    Pin(
        "ruff",
        PYPROJECT,
        r'"ruff==([0-9][^"]*)"',
        CONFIG,
        pre_commit_rev("https://github.com/astral-sh/ruff-pre-commit"),
        prefix="v",
    ),
    # Anchored on the setup-uv block: the first `version:` in the workflow belongs to whatever
    # action happens to be pinned first, and matching that would compare the wrong thing.
    Pin(
        "uv",
        WORKFLOW,
        r'astral-sh/setup-uv(?:.|\n){0,400}?version: "([^"]+)"',
        CONFIG,
        pre_commit_rev("https://github.com/astral-sh/uv-pre-commit"),
    ),
    Pin(
        "markdownlint",
        WORKFLOW,
        r"MARKDOWNLINT_VERSION: *(\S+)",
        CONFIG,
        pre_commit_rev("https://github.com/DavidAnson/markdownlint-cli2"),
    ),
    Pin(
        "gitleaks",
        WORKFLOW,
        r"GITLEAKS_VERSION: *(\S+)",
        CONFIG,
        pre_commit_rev("https://github.com/gitleaks/gitleaks"),
    ),
    # The lock is the source: pyproject only carries a floor, and the client that actually
    # ships is whatever the lock resolved. Anchored on the exact name so mlflow-skinny and
    # mlflow-tracing, which sit beside it and move together, cannot be read instead.
    Pin(
        "mlflow",
        LOCK,
        r'^name = "mlflow"\nversion = "([^"]+)"',
        pathlib.Path("docker/mlflow.Dockerfile"),
        r"FROM ghcr\.io/mlflow/mlflow:(\S+)",
        prefix="v",
    ),
)


def find(pattern: str, text: str) -> re.Match[str] | None:
    return re.search(pattern, text, re.MULTILINE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix", action="store_true", help="rewrite the mirrored version to match its source"
    )
    args = parser.parse_args()

    texts = {path: path.read_text(encoding="utf-8") for path in {p.mirror for p in PINS}}
    for pin in PINS:
        texts.setdefault(pin.source, pin.source.read_text(encoding="utf-8"))

    problems: list[str] = []
    fixed: dict[pathlib.Path, list[str]] = defaultdict(list)

    for pin in PINS:
        source_match = find(pin.source_pattern, texts[pin.source])
        mirror_match = find(pin.mirror_pattern, texts[pin.mirror])
        if source_match is None:
            problems.append(f"{pin.name}: no version found in {pin.source}")
            continue
        if mirror_match is None:
            problems.append(f"{pin.name}: no version found in {pin.mirror}")
            continue
        want = pin.prefix + source_match.group(1)
        have = mirror_match.group(1)
        if want == have:
            continue
        if args.fix:
            start, end = mirror_match.span(1)
            texts[pin.mirror] = texts[pin.mirror][:start] + want + texts[pin.mirror][end:]
            fixed[pin.mirror].append(f"{pin.name}: {have} -> {want}")
        else:
            problems.append(
                f"{pin.name} drift: {pin.mirror}={have} {pin.source}={want} "
                f"— run scripts/check_tool_pins.py --fix"
            )

    for path, changes in fixed.items():
        path.write_text(texts[path], encoding="utf-8")
        for change in changes:
            print(f"updated {change}")
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
