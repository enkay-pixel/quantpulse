"""Every CSS variable the dashboard's components use is defined in its stylesheet.

An undefined `var(--x)` is not an error anywhere: the browser drops the declaration, and a chart
line with no stroke simply is not drawn. Two charts drew an invisible line that way — the IV
term structure among them — and nothing failed. Read across the whole source tree, so a new
component cannot reintroduce it.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web" / "src"
USED = re.compile(r"var\((--[a-z0-9-]+)\)")
DEFINED = re.compile(r"^\s*(--[a-z0-9-]+)\s*:", re.M)


def test_every_variable_a_component_uses_is_defined() -> None:
    defined = set(DEFINED.findall((WEB / "index.css").read_text()))
    assert defined, "found no variables in index.css — the pattern is reading nothing"
    used: dict[str, set[str]] = {}
    for source in [*WEB.rglob("*.tsx"), *WEB.rglob("*.ts")]:
        for name in USED.findall(source.read_text()):
            used.setdefault(name, set()).add(source.name)
    assert used, "found no var() uses — the pattern is reading nothing"
    missing = {name: sorted(files) for name, files in used.items() if name not in defined}
    assert not missing, f"undefined CSS variables, which render as nothing: {missing}"
