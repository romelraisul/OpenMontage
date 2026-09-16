#!/usr/bin/env bash
# Render one programme block DETACHED, then poll for it.
#
# Why detached: a full episode takes ~3.5 min at 1080p, and cron sessions carry a
# short hard-interrupt/watchdog. A foreground render can be killed mid-encode and
# leave a half-written MP4. Detaching puts the render outside the agent's death
# radius, and the caller stays fast (start it, return, check status next shift).
#
# Usage:
#   render_programme.sh start <episode.json> <output.mp4>
#   render_programme.sh status <output.mp4>
#
# status also reports the AUDIBLE FRACTION. A file that is mostly dead air passes
# a naive mean_volume check and still airs silence — build-log-003 shipped at 5%
# audible. Anything below 50% is reported as not-ready.
#
# ponytail: single-flight via a lockfile, not a queue. Two concurrent 1080p
# renders would thrash the box; add a queue only if the fleet ever renders in
# parallel.
set -uo pipefail

COMPOSER=/home/romel/OpenMontage/remotion-composer
NODE=/home/romel/.local/bin/node
LOCK=/tmp/hostamar-render.lock
LOG=/tmp/hostamar-render.log
MIN_FRACTION=0.5

audible_fraction() {  # 10s windows, count windows with real signal
  local f="$1" dur total loud=0 i v
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null) || return 1
  [ -z "$dur" ] && return 1
  total=$(awk -v d="$dur" 'BEGIN{print int(d/10) + 1}')
  for ((i = 0; i < total; i++)); do
    v=$(ffmpeg -v info -ss $((i * 10)) -t 10 -i "$f" -af volumedetect -f null - 2>&1 \
        | grep -m1 -oE 'mean_volume: [-0-9.]+' | grep -oE '[-0-9.]+$')
    if [ -n "$v" ] && awk -v v="$v" 'BEGIN{exit !(v > -50)}'; then loud=$((loud + 1)); fi
  done
  awk -v l="$loud" -v t="$total" 'BEGIN{printf "%.2f", l / t}'
}

cmd="${1:-}"
case "$cmd" in
  start)
    props="${2:?episode json required}"
    out="${3:?output mp4 required}"
    if [ -e "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
      echo "BUSY: render already running (pid $(cat "$LOCK"))"
      exit 0
    fi
    mkdir -p "$(dirname "$out")"
    cd "$COMPOSER" || exit 1
    setsid nohup "$NODE" node_modules/@remotion/cli/remotion-cli.js render \
      src/index.tsx Explainer "$out" "--props=$props" \
      --concurrency=2 --log=error > "$LOG" 2>&1 &
    echo $! > "$LOCK"
    echo "STARTED pid $(cat "$LOCK") -> $out"
    ;;
  status)
    out="${2:?output mp4 required}"
    if [ -e "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
      echo "RENDERING pid $(cat "$LOCK")"
      exit 0
    fi
    if [ -s "$out" ]; then
      # a real file, not a truncated one: ffprobe must report a duration
      dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$out" 2>/dev/null)
      if [ -n "$dur" ]; then
        frac=$(audible_fraction "$out")
        if awk -v f="$frac" -v m="$MIN_FRACTION" 'BEGIN{exit !(f >= m)}'; then
          echo "DONE ${out} duration=${dur}s audible=${frac} size=$(stat -c%s "$out")B"
        else
          echo "SILENT-ISH ${out} duration=${dur}s audible=${frac} (need >=${MIN_FRACTION})" \
               "— narrate before publishing: python3 scripts/build_programme.py:narrate_scenes"
        fi
      else
        echo "BAD: $out exists but is not a valid video (truncated render?)"
      fi
    else
      echo "FAILED: no output at $out"
      tail -5 "$LOG" 2>/dev/null
    fi
    ;;
  *)
    echo "usage: $0 {start <json> <mp4>|status <mp4>}" >&2
    exit 2
    ;;
esac
