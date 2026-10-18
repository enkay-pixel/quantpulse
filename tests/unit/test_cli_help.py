"""Every command's help renders as written.

argparse formats help text with `%`, so a bare percent sign (`5% stakes`) does not fail: it prints
the parser's internal dictionary in the middle of the sentence, and only someone reading `--help`
notices. Rendering every command's help is the whole check.
"""

import re

import pytest

from quantpulse import cli


def _help(capsys: pytest.CaptureFixture[str], *argv: str) -> str:
    with pytest.raises(SystemExit) as exc:
        cli.main([*argv, "--help"])
    assert exc.value.code == 0
    return capsys.readouterr().out


def test_every_command_help_renders_without_parser_internals(
    capsys: pytest.CaptureFixture[str],
) -> None:
    top = _help(capsys)
    assert "option_strings" not in top
    commands = re.search(r"\{([a-z,-]+)\}", top)
    assert commands, "the command list was not found in the top-level help"
    for command in commands.group(1).split(","):
        assert "option_strings" not in _help(capsys, command), command
