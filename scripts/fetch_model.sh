#!/usr/bin/env bash
# Resilient big-file fetch from HuggingFace.
#
# Why this exists: this box's pipe to HF's CDN stalls to ~0 B/s partway through
# multi-GB files (observed: 1.6G then dead; recovery to 197 B/s). A single
# `hf download` then sits forever at 0%. This loop watches staged bytes and
# restarts the client when stalled — the Rust `hf` client resumes `.incomplete`
# partials, so progress is never lost.
#
# DO NOT use hf_transfer here: it DELETES the partial on start (observed: 1.5G
# wiped) instead of resuming.
#
# Usage: fetch_model.sh <repo> <include-pattern> <local-dir> [max-attempts]
#
# ponytail: stall detection is "bytes unchanged for 120s", not a speed test.
# A speed test would need a baseline that varies by hour; unchanged-bytes is
# the only signal that matters (stalled vs moving).
set -uo pipefail

REPO="${1:?repo required}"; PATTERN="${2:?include pattern required}"
DESTDIR="${3:?local dir required}"; MAX="${4:-50}"
STABLE_SECS=120

export PATH="/home/romel/.local/bin:$PATH"
mkdir -p "$DESTDIR"

bytes() { du -sb "$DESTDIR" 2>/dev/null | cut -f1; }

attempt=0
while [ "$attempt" -lt "$MAX" ]; do
  attempt=$((attempt + 1))
  if ls "$DESTDIR"/*.safetensors 2>/dev/null | grep -qv ".incomplete"; then
    f=$(ls -la "$DESTDIR"/*.safetensors 2>/dev/null | head -1)
    echo "DONE attempt=$attempt file: $f"
    exit 0
  fi
  echo "attempt $attempt/$MAX ..."
  hf download "$REPO" --include "$PATTERN" --local-dir "$DESTDIR" >/tmp/fetch-model.log 2>&1 &
  pid=$!
  last=$(bytes); still=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 20
    now=$(bytes)
    if [ "$now" -gt "$last" ]; then last=$now; still=0; else still=$((still + 20)); fi
    if [ "$still" -ge "$STABLE_SECS" ]; then
      echo "  stalled at $((now/1024/1024))MB for ${STABLE_SECS}s — restarting client (partial kept)"
      kill "$pid" 2>/dev/null; sleep 3; kill -9 "$pid" 2>/dev/null; break
    fi
  done
  wait "$pid" 2>/dev/null && echo "  client exited clean"
done
echo "FAILED after $MAX attempts"; tail -3 /tmp/fetch-model.log; exit 1
