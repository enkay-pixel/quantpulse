"""Small shared helpers."""

from collections.abc import Iterator, Sequence

# Postgres allows at most 65,535 bind parameters per statement, and a multi-row insert spends one
# per column per row. 2,000 rows keeps a table of up to 32 columns under it. It was 4,000, which
# the 19-column option tables overflow at 3,450 rows: SPY's chain reached 3,021 on one day.
# `tests/unit/test_bulk_writes.py` holds every table to it, and every bulk insert to `chunked`.
POSTGRES_MAX_BIND_PARAMS = 65_535
UPSERT_CHUNK_ROWS = 2000


def chunked[T](items: Sequence[T], size: int = UPSERT_CHUNK_ROWS) -> Iterator[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
