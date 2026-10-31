"""The Dependabot follow-up keeps write access away from anything the PR brings.

The workflow commits to Dependabot's PR branches, so it holds a token that can push. Resolving the
PR's lock can build a package fetched from PyPI, which runs that package's code. The workflow is
safe only while those two never share a job: the job that resolves can read and nothing more, and
stores no credentials for a later step to find, and the job that pushes runs nothing but git and
gh over a patch limited to the files the repairs may change. One added `permissions` line or one
`uv` step in the wrong job would undo that, and nothing else would fail, so it is held here.
"""

import re
import shlex
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _jobs() -> dict:
    return yaml.safe_load((WORKFLOWS / "dependabot-follow-up.yml").read_text())["jobs"]


def _runs(job: dict) -> list[str]:
    return [step["run"] for step in job["steps"] if "run" in step]


SHELL_KEYWORDS = {"if", "then", "else", "elif", "fi", "do", "done", "!", "{", "}"}
# Tokens after which the shell expects a new command; `$(` lexes as `$` then `(`.
STARTS_A_COMMAND = {"|", "||", "&&", ";", "&", "("}
# A redirection is not one: the word after it is a file or a string, not a program.
REDIRECTIONS = {">", ">>", "<", "<<<"}


def _commands(script: str) -> set[str]:
    """The program each command in a run block starts, with quoting read the way bash reads it."""
    commands = set()
    for line in script.splitlines():
        expecting, target = True, False
        for token in shlex.shlex(line, posix=True, punctuation_chars=True):
            if target:
                target = False
            elif token == "$":
                continue
            elif token in REDIRECTIONS:
                target = True
            elif token in STARTS_A_COMMAND:
                expecting = True
            elif expecting and token not in SHELL_KEYWORDS and not re.match(r"\w+=", token):
                commands.add(token)
                expecting = False
    return commands


def test_the_job_that_resolves_can_only_read() -> None:
    prepare = _jobs()["prepare"]
    assert prepare["permissions"] == {"contents": "read"}
    checkout = next(s for s in prepare["steps"] if s.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["persist-credentials"] is False


def test_the_job_that_pushes_runs_no_code_from_the_pr() -> None:
    push = _jobs()["push"]
    assert set(push["permissions"]) == {"contents", "actions"}
    commands = set().union(*(_commands(script) for script in _runs(push)))
    # Shell builtins and the tools that move the patch; anything else could be the PR's code.
    unexpected = commands - {"git", "gh", "echo", "exit", "grep", "cut", "[", "true"}
    assert not unexpected, f"the push job must run only git and gh over the patch: {unexpected}"
    allowlist = next(s for s in _runs(push) if "allowed=" in s)
    assert ".github" not in allowlist, "the workflow token cannot push workflow files"


def test_ci_can_be_dispatched_onto_the_follow_up_commit() -> None:
    """The follow-up's own push starts no workflow, so without this the PR waits on CI forever."""
    ci = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())
    # PyYAML reads the bare key `on` as the boolean True.
    assert "workflow_dispatch" in ci[True]
