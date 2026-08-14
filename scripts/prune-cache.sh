#!/usr/bin/env bash
# Reclaim Docker build cache, but only once it is actually large.
#
# Repeated `make build` accumulates BuildKit layer cache without bound — 20 GB over ten days
# here, which is why this exists at all. The uv wheel cache (type=exec.cachemount) is
# deliberately KEPT: it is what lets a rebuild survive a flaky connection by resuming
# downloads instead of restarting ~200 wheels, and it is ~1 GB against the ~19 GB of layer
# cache worth reclaiming.
#
# Gated on size rather than run unconditionally, because pruning is not free: it costs the
# next build every layer step above the wheel cache. Against a cache of a few GB on a disk
# with plenty free, running it weekly buys nothing but a slower next build. A runaway cache
# is the case this exists for; an ordinary week is not, and below the ceiling it is a no-op
# that says so.
set -uo pipefail

# Whether pruning reclaims host disk depends on the Docker Desktop storage driver. Under
# overlay2 the VM's disk image grew monotonically and discards never reached the host, so a
# prune could only stop the file getting larger. Under the containerd snapshotter the space
# does come back — measured here as several GB off the disk image after an ordinary prune.
# The mechanism is inferred from the driver change rather than verified directly; the
# reclaim itself is measured.
#
# The ceiling stays where it is regardless, because the cost side is unchanged: a full
# rebuild's cache sits just under it, so the next build still starts warm. Lowering it would
# prune a cache that is doing its job to reclaim space on a disk that is not short of it.
CEILING_GB="${PRUNE_CEILING_GB:-10}"

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

if ! docker info >/dev/null 2>&1; then
    # Docker Desktop closed is the normal state while travelling, not a failure.
    log "docker is not running — nothing to prune"
    exit 0
fi

# `docker system df` reports the cache with a unit suffix (3.157GB, 512.3MB). Normalised to
# GB here so the comparison does not silently treat 800MB as larger than 12GB.
gb=$(docker system df 2>/dev/null | awk '/^Build Cache/ {
    v = $(NF-1); g = v + 0; u = v; sub(/^[0-9.]+/, "", u);
    if (u == "MB") g /= 1024;
    else if (u == "kB" || u == "KB") g /= 1048576;
    else if (u == "B") g /= 1073741824;
    else if (u == "TB") g *= 1024;
    printf "%.2f", g
}')

if [ -z "$gb" ]; then
    log "could not read the build cache size — skipping rather than guessing"
    exit 0
fi

if awk -v a="$gb" -v b="$CEILING_GB" 'BEGIN { exit !(a > b) }'; then
    log "build cache ${gb} GB exceeds ${CEILING_GB} GB — pruning (uv wheel cache kept)"
    docker builder prune --force --filter "type!=exec.cachemount"
    docker image prune --force
    docker system df
else
    log "build cache ${gb} GB is under ${CEILING_GB} GB — keeping it so builds stay warm"
fi
