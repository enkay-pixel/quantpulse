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
# next build every layer step above the wheel cache. Run weekly against a cache sitting at
# ~3 GB with ~287 GB free, the only thing it reliably bought was a slower Monday. The 20 GB
# incident is the case this is for; an ordinary week is not. Below the ceiling this is a
# no-op that says so.
set -uo pipefail

# Lowered from 12 on 2026-08-02. This comment claimed until 2026-08-09 that Docker.raw grows
# monotonically and NEVER shrinks on macOS, so pruning could not recover host disk and could
# only stop the file getting permanently larger. That was true of Docker Desktop 4.45 and is
# no longer true. Both measurements stand; the version changed underneath them:
#
#   4.45  fstrim inside the VM freed 114 MiB in-VM and 0 MB on the host. One `make build`
#         took Docker.raw 11.6 -> 14.5 GB and the 2.9 GB never came back.
#   4.85  this script reclaimed 7.01 GB of build cache and Docker.raw fell 16,661 -> 9,976 MB
#         (du, stable on re-measure; apparent size is ~471 GB and always was — sparse).
#         Host free went 291 -> 297 GB.
#
# The visible difference is the storage driver: 4.85 with engine 29.6.2 reports overlayfs on
# io.containerd.snapshotter.v1, where 4.45 used overlay2. That discards now reach the host
# sparse file is the obvious reading and it matches the numbers, but it was NOT verified
# directly — treat the mechanism as inferred and the reclaim itself as measured. There is no
# `docker desktop disk` command in 4.85 either; the space came back as a side effect of the
# ordinary prune, not from anything asked for.
#
# The ceiling stays at 10 even though pruning now pays back on the host, because the cost
# side is unchanged: at 8.53 GB a full rebuild's cache sits just under it, so the next build
# still starts warm. Lowering it would prune a cache that is doing its job to reclaim space
# on a disk with 297 GB free. The premise moved; the number it implies did not.
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
