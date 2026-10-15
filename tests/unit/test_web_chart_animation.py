"""Every chart series in the dashboard is drawn without its entry animation.

recharts animates a series in by default, drawing the line from nothing over about a second. A
screenshot taken before that finishes shows the axes and grid with no data on them, and nothing
reports it: the README's images are taken by headless Chrome, which captures before the animation
has run, so a chart that animates appears there as an empty frame. The dashboard's convention is
`isAnimationActive={false}` on every series; this holds a new chart to it.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web" / "src"
SERIES = re.compile(r"<(Line|Area|Bar|Scatter|Pie|Radar)\b")


def opening_tag(source: str, start: int) -> str:
    """The JSX opening tag that begins at `start`, read to its closing `>`. Props hold arrow
    functions and nested objects, so a `>` inside braces does not end the tag."""
    depth = 0
    for i in range(start, len(source)):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ">" and depth == 0:
            return source[start : i + 1]
    raise AssertionError(f"unterminated tag at offset {start}")


def test_every_chart_series_is_drawn_without_animation() -> None:
    tags: list[tuple[str, str]] = []
    for path in WEB.rglob("*.tsx"):
        source = path.read_text()
        tags += [(path.name, opening_tag(source, m.start())) for m in SERIES.finditer(source)]
    assert len(tags) >= 10, f"found {len(tags)} series — the pattern is reading nothing"
    animated = [
        f"{name}: {tag.splitlines()[0].strip()} dataKey={m.group(1) if m else '?'}"
        for name, tag in tags
        if "isAnimationActive={false}" not in tag
        for m in [re.search(r'dataKey="([^"]+)"', tag)]
    ]
    assert not animated, f"series that animate in, and so screenshot as empty: {animated}"
