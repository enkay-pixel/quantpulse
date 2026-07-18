"""Small shared helpers."""

from collections.abc import Iterator, Sequence

# Postgres allows at most 65,535 bind parameters per statement; chunk bulk
# writes well below that so any table width stays safe.
UPSERT_CHUNK_ROWS = 4000


def chunked[T](items: Sequence[T], size: int = UPSERT_CHUNK_ROWS) -> Iterator[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
