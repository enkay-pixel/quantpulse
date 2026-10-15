"""Regenerate the README's dashboard screenshots from the running stack.

Each image is one dashboard tab for one market, taken by headless Google Chrome at 1440 px wide and
2x scale, the recipe the roadmap documented by hand. The by-hand version needed each tab's height
measured first, at exactly 1440 px, because a height read at any other width left a band of empty
background below the content. This removes the measurement: it shoots tall, then trims the
trailing rows that are pure background, keeping a small margin.

Needs the stack up (`make up`) and Google Chrome installed. Writes to docs/assets/; review the
images before committing them, since they show whatever the dashboard shows at that moment.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DASHBOARD = "http://localhost:8080"
ASSETS = Path(__file__).resolve().parents[1] / "docs" / "assets"
WIDTH, TALL, SCALE = 1440, 6000, 2
#: Background kept below the content, in device pixels.
MARGIN = 48
#: Colours in the saved palette. The dashboard is flat colour and anti-aliased text, so a 256-colour
#: palette is indistinguishable by eye (worst channel error ~14 of 255) and about a third the size —
#: which is what keeps a long tab under the repository's 500 KB limit on added files.
PALETTE = 256

#: (file, market, tab) — the images the README shows.
SHOTS = [
    ("dashboard.png", "XNYS", "overview"),
    ("evidence-tab.png", "XNYS", "evidence"),
    ("options-tab.png", "XNYS", "options"),
    ("model-book-tab.png", "XNYS", "model-book"),
    ("research-tab.png", "XNYS", "research"),
    ("jse-evidence.png", "XJSE", "evidence"),
]


def content_height(image: Image.Image, tolerance: int = 6) -> int:
    """Rows down to the last one that differs from the page background, which is read from the
    bottom-right pixel of a shot taken taller than any tab."""
    rgb = image.convert("RGB")
    background = rgb.getpixel((rgb.width - 1, rgb.height - 1))
    assert isinstance(background, tuple)
    for y in range(rgb.height - 1, -1, -1):
        row = rgb.crop((0, y, rgb.width, y + 1)).getcolors(maxcolors=rgb.width + 1) or []
        colours = (c for _, c in row if isinstance(c, tuple))
        if any(max(abs(c[i] - background[i]) for i in range(3)) > tolerance for c in colours):
            return y + 1
    return 0


def shoot(market: str, tab: str, out: Path, budget_ms: int) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.png"
        subprocess.run(
            [
                CHROME,
                "--headless",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--force-device-scale-factor={SCALE}",
                f"--window-size={WIDTH},{TALL}",
                f"--virtual-time-budget={budget_ms}",
                f"--screenshot={raw}",
                f"{DASHBOARD}/?market={market}#{tab}",
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        with Image.open(raw) as image:
            height = content_height(image)
            if height == 0:
                raise RuntimeError(f"{market} #{tab} rendered nothing — is the stack up?")
            if height >= image.height:
                raise RuntimeError(f"{market} #{tab} is taller than {TALL}px; raise TALL")
            trimmed = image.crop((0, 0, image.width, min(image.height, height + MARGIN)))
            trimmed.convert("RGB").quantize(
                colors=PALETTE, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE
            ).save(out, optimize=True)
            return height // SCALE


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="Regenerate one file, e.g. research-tab.png")
    parser.add_argument("--out", type=Path, default=ASSETS, help="Directory to write into")
    parser.add_argument("--budget-ms", type=int, default=9000, help="Time for the page to load")
    args = parser.parse_args()
    if not Path(CHROME).exists():
        print(f"Google Chrome not found at {CHROME}", file=sys.stderr)
        return 1
    if args.only and args.only not in {name for name, _, _ in SHOTS}:
        print(f"{args.only} is not one of the README's screenshots", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    for name, market, tab in SHOTS:
        if args.only and name != args.only:
            continue
        css_height = shoot(market, tab, args.out / name, args.budget_ms)
        print(f"{name}: {market} #{tab}, {WIDTH}x{css_height}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
