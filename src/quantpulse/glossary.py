"""Plain-language names for every term the platform shows, read from configs/glossary.yaml.

One source for the API's field descriptions and the dashboard's labels, so a term means the same
thing wherever it appears. See the file's header for the shape of an entry.
"""

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

from quantpulse.config import get_settings


@dataclass(frozen=True)
class Term:
    label: str
    meaning: str
    term: str | None = None
    read: str | None = None

    def describe(self) -> str:
        """One paragraph: what it is called, what it is, how to read it."""
        name = f"{self.label} ({self.term})" if self.term else self.label
        text = f"{name}. {self.meaning}"
        return f"{text} How to read it: {self.read}" if self.read else text


@cache
def load(path: Path | None = None) -> dict[str, Term]:
    path = path or get_settings().quantpulse_glossary_file
    raw = yaml.safe_load(path.read_text())["terms"]
    return {key: Term(**entry) for key, entry in raw.items()}
