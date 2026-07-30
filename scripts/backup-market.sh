#!/usr/bin/env bash
# Snapshot the `market` database.
#
# Most of this database is rebuildable — prices re-download, features recompute, models
# retrain. Two things are not, and they are the reason this script exists:
#
#   * option_quotes  — live-only chains. A day not captured is gone permanently; there is
#                      no vendor to backfill it from at any price.
#   * portfolio_snapshots / predictions — the live out-of-sample record. Recreating it
#                      would mean re-scoring history with today's champion, which is the
#                      retroactive rewrite the promotion gate exists to prevent.
#
# Dumps the whole database anyway: it is only ~48 MB gzipped, and a single-file restore
# beats reasoning about foreign-key order at the moment you actually need it.
set -euo pipefail

BACKUP_DIR="${QUANTPULSE_BACKUP_DIR:-$HOME/quantpulse-backups}"
KEEP="${QUANTPULSE_BACKUP_KEEP:-14}"
CONTAINER=quantpulse-postgres
DB=market
USER_NAME=quantpulse

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

# A stopped stack is not a failure — it is the normal state while travelling. Exiting 0
# keeps launchd from reporting a problem that isn't one.
if ! docker exec "$CONTAINER" pg_isready -U "$USER_NAME" -d "$DB" >/dev/null 2>&1; then
    log "postgres is not running — nothing to back up"
    exit 0
fi

mkdir -p "$BACKUP_DIR"
target="$BACKUP_DIR/${DB}-$(date +%Y-%m-%d).sql.gz"
partial="$target.partial"

# Write to .partial, verify, then rename: a dump interrupted midway (sleep, Docker
# restart, full disk) must never be left sitting there looking like a good backup.
trap 'rm -f "$partial"' EXIT
docker exec "$CONTAINER" pg_dump -U "$USER_NAME" -d "$DB" | gzip >"$partial"
gzip -t "$partial"
mv "$partial" "$target"
trap - EXIT

# Rotate oldest-first. Portable to macOS's xargs, which has no -r.
find "$BACKUP_DIR" -name "${DB}-*.sql.gz" -type f | sort -r | tail -n "+$((KEEP + 1))" |
    while read -r old; do rm -f "$old"; done

kept=$(find "$BACKUP_DIR" -name "${DB}-*.sql.gz" -type f | wc -l | tr -d ' ')
log "wrote $(du -h "$target" | cut -f1) to $target ($kept kept)"
