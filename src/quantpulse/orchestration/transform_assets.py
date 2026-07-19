"""dbt models as Dagster assets: the transform layer joins the same lineage graph
as ingestion, ML, and serving. dbt sources map to upstream assets via meta config."""

import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

import dagster as dg

REPO_ROOT = Path(__file__).resolve().parents[3]
TRANSFORM_DIR = REPO_ROOT / "transform"

dbt_project = DbtProject(project_dir=TRANSFORM_DIR)
dbt_project.prepare_if_dev()

if not dbt_project.manifest_path.exists():
    # Cold starts (pytest, CI): install packages and parse once to produce the
    # manifest. Docker images bake it at build time instead.
    from dbt.cli.main import dbtRunner

    _flags = ["--project-dir", str(TRANSFORM_DIR), "--profiles-dir", str(TRANSFORM_DIR)]
    if not (TRANSFORM_DIR / "dbt_packages").exists():
        _deps = dbtRunner().invoke(["deps", *_flags])
        if not _deps.success:
            raise RuntimeError(f"dbt deps failed: {_deps.exception}")
    _parse = dbtRunner().invoke(["parse", *_flags])
    if not _parse.success:
        raise RuntimeError(f"dbt parse failed: {_parse.exception}")


class QuantpulseDbtTranslator(DagsterDbtTranslator):
    def get_group_name(self, dbt_resource_props: Mapping[str, Any]) -> str:
        return "transform"


@dbt_assets(
    manifest=dbt_project.manifest_path,
    dagster_dbt_translator=QuantpulseDbtTranslator(),
)
def transform_dbt_assets(context: dg.AssetExecutionContext, dbt: DbtCliResource) -> Any:
    """Run `dbt build` (models + tests) and stream results as asset events."""
    yield from dbt.cli(["build"], context=context).stream()


# Resolve dbt next to the running interpreter when it's not on PATH (e.g. pytest
# invoking an unactivated venv).
_DBT_EXECUTABLE = shutil.which("dbt") or str(Path(sys.executable).parent / "dbt")

dbt_resource = DbtCliResource(
    project_dir=dbt_project,
    profiles_dir=str(TRANSFORM_DIR),
    dbt_executable=_DBT_EXECUTABLE,
)
