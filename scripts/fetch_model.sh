#!/usr/bin/env bash
# Resilient big-file fetch (v2 — curl-based).
#
# Why curl and not `hf download`: over this box's throttled pipe the hf client
# stalls mid-file AND does not resume its `.incomplete` partial (23 attempts,
# every restart began near zero). curl `-C -` resumes against Accept-Ranges
# CDNs, and `--speed-limit/--speed-time` aborts stalled transfers natively.
# Each attempt re-hits the resolve URL so Xet signatures never go stale.
#
# Usage: fetch_model.sh <resolve-url> <dest-file> <expected-bytes> [max-attempts]
# Example: fetch_model.sh \
#   https://huggingface.co/stabilityai/sdxl-turbo/resolve/main/sd_xl_turbo_1.0_fp16.safetensors \
#   /home/romel/ComfyUI/models/checkpoints/sd_xl_turbo_1.0_fp16.safetensors \
#   6938081905
#
# Do NOT use hf_transfer here: it DELETES the partial on start.
# Do NOT auto-export HF_TOKEN: the token file on this box is dead and a dead
# token turns public pulls into 401s.
set -uo pipefail

URL="${1:?resolve url required}"
DEST="${2:?dest file required}"
EXPECTED="${3:?expected bytes required}"
MAX="${4:-200}"
PART="$DEST.part"

mkdir -p "$(dirname "$DEST")"
# adopt any orphan hf partial as the resume base
if [ ! -f "$PART" ]; then
  ORPHAN=$(find "$(dirname "$DEST")/.cache" -name "*.incomplete" 2>/dev/null | head -1)
  [ -n "$ORPHAN" ] && cp "$ORPHAN" "$PART" && echo "adopted partial: $ORPHAN"
fi

attempt=0
while [ "$attempt" -lt "$MAX" ]; do
  attempt=$((attempt + 1))
  have=$(stat -c%s "$PART" 2>/dev/null || echo 0)
  if [ "$have" -ge "$EXPECTED" ]; then
    truncate -s "$EXPECTED" "$PART" 2>/dev/null
    mv -f "$PART" "$DEST"
    echo "DONE attempt=$attempt bytes=$EXPECTED"
    exit 0
  fi
  echo "attempt $attempt/$MAX have=${have}B of ${EXPECTED}B ..."
  # --speed-time: abort when under 1KB/s for 180s (stall, not slowness).
  # ponytail: 1KB/s floor, not a target — slower-than-that still aborts even
  # if bytes move, because at that rate 7G takes 80+ days. Raise the floor,
  # never lower it.
  curl -sL -C - --speed-limit 1000 --speed-time 180 --retry 0 \
    -o "$PART" "$URL" 2>/tmp/fetch-curl.err
  rc=$?
  echo "  curl exit=$rc have=$(stat -c%s "$PART" 2>/dev/null || echo 0)B"
  sleep 5
done
echo "FAILED after $MAX attempts"; exit 1
