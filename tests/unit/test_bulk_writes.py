"""No bulk insert can pass Postgres's limit of 65,535 bind parameters in one statement.

A multi-row insert spends one parameter per column per row, so a write that fits for years stops
the night its rows outgrow the limit. The paper book did on 2026-11-07: it wrote each market's whole
history in one statement, and Frankfurt's passed it (incident 41). The rule was already written down
("bulk upserts go through `chunked`"); these tests hold the code to it, and hold the batch size to
the widest table, which the old 4,000 rows did not (19 columns x 4,000 = 76,000).
"""

import ast
from pathlib import Path

from quantpulse.db.base import Base
from quantpulse.utils import POSTGRES_MAX_BIND_PARAMS, UPSERT_CHUNK_ROWS

SRC = Path(__file__).resolve().parents[2] / "src" / "quantpulse"
INSERTS = {"insert", "pg_insert"}
# What a loop must name to count as batching: the helper, or the size it slices by.
BATCHERS = {"chunked", "UPSERT_CHUNK_ROWS"}


def _bulk_values_calls(tree: ast.AST) -> list[ast.Call]:
    """`insert(T).values(rows)` with one positional argument that is not a single row's dict."""
    found = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "values"
            and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Name)
            and node.func.value.func.id in INSERTS
        ):
            continue
        if len(node.args) == 1 and not isinstance(node.args[0], ast.Dict):
            found.append(node)
    return found


def _in_a_batching_loop(call: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    node: ast.AST | None = call
    while node is not None:
        if isinstance(node, ast.For):
            named = {n.id for n in ast.walk(node.iter) if isinstance(n, ast.Name)}
            if named & BATCHERS:
                return True
        node = parents.get(node)
    return False


def _sites() -> list[tuple[str, int, bool]]:
    sites = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        parents = {
            child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
        }
        for call in _bulk_values_calls(tree):
            sites.append(
                (
                    f"{path.relative_to(SRC)}:{call.lineno}",
                    call.lineno,
                    _in_a_batching_loop(call, parents),
                )
            )
    return sites


def test_every_bulk_insert_is_written_in_batches() -> None:
    sites = _sites()
    # Guards the guard: a matcher that finds nothing passes everything.
    files = {s.split(":")[0] for s, _, _ in sites}
    assert "ml/portfolio.py" in files, "the paper book's write is the one that broke"
    assert len(sites) >= 10, f"found only {len(sites)} bulk inserts; has the matcher broken?"
    unbatched = [site for site, _, batched in sites if not batched]
    assert not unbatched, (
        "each of these inserts a list of rows in one statement, which fails once the rows "
        f"outgrow 65,535 parameters; write them through `chunked`: {unbatched}"
    )


def test_a_full_batch_of_the_widest_table_fits_in_one_statement() -> None:
    widest = max(Base.metadata.tables.values(), key=lambda table: len(table.columns))
    params = UPSERT_CHUNK_ROWS * len(widest.columns)
    assert params <= POSTGRES_MAX_BIND_PARAMS, (
        f"{UPSERT_CHUNK_ROWS} rows of {widest.name} ({len(widest.columns)} columns) is {params} "
        "parameters; lower UPSERT_CHUNK_ROWS"
    )
