# Programme block — how Hostamar TV makes real episodes

## Why

Every item on the channel was a 15-second Receipt render. The whole playlist came to
~13 minutes looping ~100x/day. That is the exact shape YouTube's *inauthentic content*
policy removes channels for: repetitive, mass-produced, no original audio. Retiring the
third-party footage fixed the *provenance* problem; this fixes the *volume and variety*
problem.

## What a programme block is

A chaptered, narrated, long-form episode — like a real channel's magazine show, not a
loop of stings. Built from the Explainer composition that already lives in
`remotion-composer` (no new Remotion components were written; the existing vocabulary
already covers a magazine format).

Episode shape:

```
ident (hero_title, 6s)
  1. <chapter title> (text_card, 4s)     <- every chapter opens with a title card
     scene, scene, ...                    <- text_card / stat_card / kpi_grid /
  2. <chapter title> (text_card, 4s)         bar_chart / comparison / callout /
     scene, scene, ...                         terminal_scene / screenshot_scene
outro (callout, 8s)
```

Narration: one `edge-tts` track muxed under the whole episode. edge-tts is free and
installed, so the audio is genuinely ours — no third-party music, no licensed bed.

## Build one

```bash
cd ~/OpenMontage
python3 scripts/build_programme.py          # self-check: asserts the episode is >60s,
                                            # has an ident, chapter cards, no overlaps
```

Then, for a real episode:

```python
import sys; sys.path.insert(0, 'scripts')
from build_programme import build_episode, write_props, narrate, render, mux_narration

cuts, secs, narration = build_episode("Build Log 002", [
    {"title": "Chapter name", "narration": "what the voice says",
     "scenes": [(20, {"type": "text_card", "text": "on screen"}),
                (20, {"type": "stat_card", "stat": "50", "subtitle": "units"})]},
])
write_props(cuts, "projects/programmes/build-log-002.json")
narrate(narration, "/tmp/narr.mp3")
render("projects/programmes/build-log-002.json", "/tmp/ep.mp4")
mux_narration("/tmp/ep.mp4", "/tmp/narr.mp3", "projects/programmes/build-log-002.mp4")
```

## Scene vocabulary (must exist in Explainer.tsx — don't invent types)

`hero_title` (ident), `text_card`, `stat_card`, `callout`, `comparison`,
`bar_chart`, `line_chart`, `pie_chart`, `kpi_grid`, `progress_bar`,
`terminal_scene`, `screenshot_scene`, `anime_scene`.

A scene with an unknown `type` renders an empty frame — it does not error, so check the
output duration, not just exit code.

## Verified recipe (measured, not assumed)

- Render: `node node_modules/@remotion/cli/remotion-cli.js render src/index.tsx Explainer <out> --props=<props.json> --concurrency=2`
  from `~/OpenMontage/remotion-composer`. Absolute paths — relative `node_modules/.bin`
  resolution fails in some shell contexts.
- 59s @ 1080p rendered in ~3.5 min on this box, 3.4 MB, h264+aac.
- Mux narration with `-af apad -shortest`. **Without `apad`, `-shortest` truncates the
  VIDEO to the narration length** (59s became 11.7s).
- Verify with `ffprobe` duration AND `volumedetect` mean_volume — a file can have an
  `aac` stream that is digital silence.

## Channel rules (why this exists)

1. No third-party footage on our properties. Our renders only.
2. Every episode needs original audio (edge-tts narration) — silent renders are not
   programmes.
3. Vary chapters and subjects between episodes; a repeated near-identical block is the
   removal trigger even when it is our own content.
4. Streams over 12 hours are not archived, so they earn zero public watch hours toward
   monetization. Keep episodes as uploaded videos (they are watchable and count) and
   treat the 24/7 stream as distribution, not as the asset.
