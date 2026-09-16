#!/usr/bin/env python3
"""
Programme block builder — Hostamar TV.

Why this exists: every item on the channel was a 15-second Receipt render, so the
whole playlist was ~13 minutes looping ~100x/day. That is the exact shape
YouTube's inauthentic-content policy removes channels for (repetitive,
mass-produced, no original audio). A real channel needs PROGRAMMES: long-form,
chaptered, narrated.

This builds one episode as an Explainer cut-list (the composition already exists
in remotion-composer and handles hero titles, chapter cards, charts, KPIs and
captions), then muxes a narration track so the programme has original audio.

Skipped on purpose: no new Remotion components (the vocabulary in Explainer.tsx
already covers a magazine format), no TTS service (edge-tts is installed and
free), no scheduler (the TV operator lane owns scheduling).

ponytail: narration is one edge-tts track laid under the whole episode rather
than per-scene synthesis. Per-scene would need word-level timing to stay in
sync; add that only if the drift is visible on air.
"""
import json
import os
import subprocess
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
COMPOSER = os.path.join(ROOT, "remotion-composer")
OUT = os.path.join(ROOT, "projects", "programmes")
FPS = 30


# --------------------------------------------------------------------------
# Episode definition: chaptered, each chapter a list of scenes.
# A scene is (seconds, cut-dict). The cut type must be one Explainer supports.
# --------------------------------------------------------------------------
def build_episode(topic, chapters, brand="HOSTAMAR TV"):
    """chapters: [{"title": str, "narration": str, "scenes": [(secs, cut), ...]}]"""
    cuts = []
    t = 0.0
    cuts.append({
        "id": "ident", "source": "", "in_seconds": t, "out_seconds": t + 6,
        "type": "hero_title", "text": brand,
        "heroSubtitle": f"Episode — {topic}", "subtitle": f"{date.today():%d %B %Y}",
    })
    t += 6
    for ci, ch in enumerate(chapters, 1):
        for si, (secs, cut) in enumerate(ch["scenes"]):
            c = dict(cut)
            c["id"] = f"c{ci}s{si}"
            c["source"] = c.get("source", "")
            c["in_seconds"] = t
            c["out_seconds"] = t + secs
            # a chapter opens with its own title card, like a real programme
            if si == 0:
                cuts.append({
                    "id": f"c{ci}title", "source": "",
                    "in_seconds": t, "out_seconds": t + 4,
                    "type": "text_card",
                    "text": f"{ci}. {ch['title']}",
                })
                t += 4
                c["in_seconds"] = t
                c["out_seconds"] = t + secs
            cuts.append(c)
            t += secs
    cuts.append({
        "id": "outro", "source": "", "in_seconds": t, "out_seconds": t + 8,
        "type": "callout", "callout_type": "info", "title": "Next",
        "text": "Hostamar — build, ship, host. hostamar.com",
    })
    t += 8
    total_secs = int(round(t))
    narration = "\n".join(
        f"{ch['title']}. {ch['narration']}" for ch in chapters
    )
    return cuts, total_secs, narration


def write_props(cuts, path, fps=FPS):
    props = {"cuts": cuts, "overlays": [], "captions": [], "audio": {}}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(props, fh, indent=1, ensure_ascii=False)
    return props


PIPER_VOICE = os.environ.get(
    "HOSTAMAR_PIPER_VOICE",
    "/home/romel/voices/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
)


def narrate_piper(text, out_wav, voice=PIPER_VOICE):
    """In-house narration. No account, no network, no key — runs on this box."""
    if not (voice and os.path.exists(voice)):
        return None
    with open("/tmp/piper-narr.txt", "w", encoding="utf-8") as fh:
        fh.write(text)
    r = subprocess.run(
        ["piper", "-m", voice, "-i", "/tmp/piper-narr.txt", "-f", out_wav],
        capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_wav):
        return None
    # wav -> mp3 so the mux path stays identical
    mp3 = os.path.splitext(out_wav)[0] + ".mp3"
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", out_wav, "-c:a", "libmp3lame",
         "-b:a", "128k", mp3],
        capture_output=True, text=True)
    return mp3 if r.returncode == 0 and os.path.getsize(mp3) > 0 else None


def narrate(text, out_mp3, voice="en-US-GuyNeural"):
    """edge-tts is installed and free — original audio, no API key.

    Falls back to in-house piper when edge-tts is unreachable, so a network
    outage never blocks a programme render. ponytail: piper is the fallback,
    not the default — edge-tts voices sound human; piper sounds like a robot.
    Swap the order only if offline narration matters more than voice quality.
    """
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return narrate_piper(text, os.path.splitext(out_mp3)[0] + ".wav")
    import asyncio
    import edge_tts

    async def _go():
        await edge_tts.Communicate(text, voice).save(out_mp3)

    try:
        asyncio.run(_go())
    except Exception:
        return narrate_piper(text, os.path.splitext(out_mp3)[0] + ".wav")
    if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 0:
        return out_mp3
    return narrate_piper(text, os.path.splitext(out_mp3)[0] + ".wav")


def render(props_path, out_mp4, concurrency=2):
    """Render the Explainer composition to MP4 at 1080p."""
    cmd = [
        "node_modules/.bin/remotion", "render", "src/index.tsx", "Explainer",
        out_mp4, f"--props={props_path}", "--concurrency", str(concurrency),
        "--log=error",
    ]
    return subprocess.run(cmd, cwd=COMPOSER, capture_output=True, text=True)


def mux_narration(video, audio, out):
    """Original audio track under the picture.

    No -shortest: narration is usually shorter than the episode, and -shortest
    truncates the VIDEO to the audio length (a 59s programme became 11.7s). Pad
    the audio to the picture instead so the episode keeps its full runtime.
    """
    cmd = [
        "ffmpeg", "-y", "-i", video, "-i", audio,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-map", "0:v:0", "-map", "1:a:0",
        "-af", "apad", "-shortest", out,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,codec_name",
         "-of", "json", path],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        dur = float(d["format"]["duration"])
        streams = sorted(s["codec_type"] for s in d.get("streams", []))
        return dur, streams
    except Exception:
        return None, []


if __name__ == "__main__":
    # self-check: the builder must produce a chaptered, long-form, narrated episode
    cuts, secs, narration = build_episode("Self-test", [
        {"title": "What we build", "narration": "We build agents.",
         "scenes": [(20, {"type": "text_card", "text": "Agent Cloud"}),
                    (20, {"type": "stat_card", "stat": "50", "subtitle": "renders"})]},
        {"title": "Why it matters", "narration": "It ships today.",
         "scenes": [(25, {"type": "kpi_grid", "chartData": [{"label": "x", "value": 1}]})]},
    ])
    assert secs > 60, f"episode too short for a programme block: {secs}s"
    assert any(c["type"] == "hero_title" for c in cuts), "missing ident"
    assert sum(1 for c in cuts if c["id"].endswith("title")) >= 2, \
        "chapters must open with a title card"
    # no overlaps, strictly ordered — the concat timeline depends on it
    for a, b in zip(cuts, cuts[1:]):
        assert a["out_seconds"] <= b["in_seconds"] + 0.01, f"overlap at {a['id']}"
    assert narration.strip(), "narration must not be empty"
    print(f"OK  episode={secs}s  cuts={len(cuts)}  chapters=2  narration={len(narration)} chars")
    print(f"    scene types: {sorted({c.get('type') for c in cuts})}")
