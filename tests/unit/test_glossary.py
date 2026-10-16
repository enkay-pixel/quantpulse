"""Every term the platform shows is explained, in one place, the same way everywhere.

The point is that the dashboard and the API can be read without a guidebook: a field or a model
input without a plain-language entry should fail here, not reach a page as `alpha_t_stat`.
"""

import importlib.util
import json
from pathlib import Path

import pytest

from quantpulse import glossary
from quantpulse.api.app import _BUILT_IN_SCHEMAS, create_app
from quantpulse.features.engineering import FEATURE_COLUMNS

ROOT = Path(__file__).resolve().parents[2]


def _undescribed(spec: dict[str, object]) -> list[str]:
    schemas = spec["components"]["schemas"]  # type: ignore[index]
    return sorted(
        f"{name}.{field}"
        for name, schema in schemas.items()
        if name not in _BUILT_IN_SCHEMAS
        for field, prop in schema.get("properties", {}).items()
        if not prop.get("description") or not prop.get("title")
    )


@pytest.fixture(autouse=True)
def _fresh_glossary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)
    glossary.load.cache_clear()


def test_every_api_field_has_a_plain_name_and_an_explanation() -> None:
    missing = _undescribed(create_app().openapi())
    assert not missing, f"add these to configs/glossary.yaml: {missing}"


def test_a_field_dropped_from_the_glossary_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard above has to be able to fail: remove one entry and it must name the field."""
    text = (ROOT / "configs/glossary.yaml").read_text()
    start = text.index("  sharpe:\n")
    end = text.index("  rolling_sharpe_63d:\n")
    trimmed = tmp_path / "glossary.yaml"
    trimmed.write_text(text[:start] + text[end:])
    monkeypatch.setenv("QUANTPULSE_GLOSSARY_FILE", str(trimmed))
    from quantpulse.config import get_settings

    get_settings.cache_clear()
    try:
        missing = _undescribed(create_app().openapi())
    finally:
        get_settings.cache_clear()
    assert "PhaseStats.sharpe" in missing


def test_every_model_input_has_a_plain_name() -> None:
    """The drift panel names each input; `ma_ratio_63` on its own explains nothing."""
    terms = glossary.load()
    assert not [f for f in FEATURE_COLUMNS if f not in terms]


def test_the_published_copies_match_the_glossary() -> None:
    spec = importlib.util.spec_from_file_location("export", ROOT / "scripts/export_glossary.py")
    assert spec and spec.loader
    export = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(export)
    committed = (ROOT / "web/src/lib/glossary.json").read_text()
    assert committed == export.render(), "run `make glossary` after editing configs/glossary.yaml"
    assert json.loads(committed), "the dashboard copy is empty"
    page = (ROOT / "docs/glossary.md").read_text()
    assert page == export.render_page(), "run `make glossary` after editing configs/glossary.yaml"


def test_every_entry_says_what_it_is() -> None:
    for key, term in glossary.load().items():
        assert term.label.strip() and term.meaning.strip(), key
        assert term.meaning.rstrip().endswith("."), f"{key}: meaning should be a full sentence"
