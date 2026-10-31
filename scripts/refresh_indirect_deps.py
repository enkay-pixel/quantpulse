#!/usr/bin/env python3
"""Move the lock's indirect dependencies to their newest compatible releases.

Dependabot's uv updates move only the packages pyproject.toml names. Everything those pull in
stays at the version it was first locked at, unless it has a security advisory, until a direct
bump needs a newer one. Then it moves mid-round, never tested on its own: on 2026-10-31 pytest
9.2 needed anyio 4.15, and anyio 4.15 deprecated an alias that starlette's test client still
used. The Dependabot follow-up workflow runs this on the weekly python-deps PR, so the packages
underneath move in the same round as the ones on top and are tested with them.

The direct dependencies stay where the lock has them: they are Dependabot's, under the ignore
rules in .github/dependabot.yml. If the resolver can only take the upgrades by moving one of
them, that is a decision rather than a refresh, so the lock is restored and the run fails naming
the package.
"""

import pathlib
import re
import subprocess
import sys
import tomllib

LOCK = pathlib.Path("uv.lock")
PYPROJECT = pathlib.Path("pyproject.toml")


def normalize(name: str) -> str:
    """The PEP 503 form, which is how uv.lock spells every name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement)
    if match is None:
        raise ValueError(f"cannot read a package name from {requirement!r}")
    return normalize(match.group(0))


def direct_dependencies(pyproject: dict) -> set[str]:
    project = pyproject["project"]
    requirements = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        requirements.extend(extra)
    return {requirement_name(r) for r in requirements}


def locked_versions(text: str) -> dict[str, str]:
    """Each locked package's version. This lock holds one version of each, which is checked."""
    versions: dict[str, str] = {}
    for package in tomllib.loads(text)["package"]:
        name = package["name"]
        if name in versions:
            raise SystemExit(f"{name} is locked at more than one version; compare by hand")
        versions[name] = package.get("version", "")
    return versions


def main() -> int:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = normalize(pyproject["project"]["name"])
    direct = direct_dependencies(pyproject)

    before_text = LOCK.read_text(encoding="utf-8")
    before = locked_versions(before_text)
    indirect = sorted(set(before) - direct - {project})

    command = ["uv", "lock"]
    for name in indirect:
        command += ["--upgrade-package", name]
    subprocess.run(command, check=True)

    after = locked_versions(LOCK.read_text(encoding="utf-8"))
    moved_direct = sorted(n for n in direct if n in before and before.get(n) != after.get(n))
    if moved_direct:
        LOCK.write_text(before_text, encoding="utf-8")
        for name in moved_direct:
            print(
                f"{name} is a direct dependency and would move {before[name]} -> "
                f"{after.get(name, 'removed')}; lock restored",
                file=sys.stderr,
            )
        return 1

    changes = [
        f"{name} {before[name]} -> {after[name]}"
        for name in sorted(set(before) & set(after))
        if before[name] != after[name]
    ]
    changes += [f"{name} {after[name]} (new)" for name in sorted(set(after) - set(before))]
    changes += [f"{name} {before[name]} (removed)" for name in sorted(set(before) - set(after))]
    for change in changes:
        print(change)
    if not changes:
        print(f"{len(indirect)} indirect dependencies: all at their newest compatible release")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
