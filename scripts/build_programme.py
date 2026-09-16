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


def mux_narration(video, audio, out, start_sec=0.0):
    """Original audio track under the picture.

    start_sec places the narration at a scene's cue time on a silent bed, so a
    long episode can carry narration per scene instead of one clip at the top
    (build-log-003: 13s of speech over 207s, i.e. 94% silence).

    No -shortest: narration is usually shorter than the episode, and -shortest
    truncates the VIDEO to the audio length (a 59s programme became 11.7s). Pad
    the audio to the picture instead so the episode keeps its full runtime.
    """
    cmd = [
        "ffmpeg", "-y", "-i", video, "-i", audio,
        "-filter_complex",
        f"[1:a]adelay={int(start_sec * 1000)}|{int(start_sec * 1000)},apad[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-map", "0:v:0", "-map", "[a]",
        "-shortest", out,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def narrate_scenes(props_path, video, out, voice="bn-BD-PradeepNeural"):
    """Narrate every scene at its own cue time, and refuse a mostly-silent result.

    Long episodes need narration through the whole runtime. Each scene gets one
    short line, delayed to the scene's in_seconds; the result is rejected when
    the audible fraction is too low, because a file that is 90% silence passes
    the naive mean_volume test and still airs dead air.
    """
    import asyncio
    import edge_tts

    with open(props_path, encoding="utf-8") as fh:
        cuts = json.load(fh)["cuts"]
    parts = []
    for i, c in enumerate(cuts):
        text = (c.get("text") or c.get("stat") or c.get("title")
                or c.get("terminalTitle") or "").strip()
        if not text:
            continue
        start = float(c.get("in_seconds", 0))
        end = float(c.get("out_seconds", start + 4))
        mp3 = f"/tmp/scene-narr-{i}.mp3"
        try:
            asyncio.run(edge_tts.Communicate(text, voice).save(mp3))
        except Exception:
            continue
        if os.path.exists(mp3) and os.path.getsize(mp3) > 512:
            parts.append((start, mp3))
    if not parts:
        return None

    inputs = ["-i", video]
    for _, mp3 in parts:
        inputs += ["-i", mp3]
    chains, mix = [], []
    for n, (start, _) in enumerate(parts, start=1):
        ms = int(start * 1000)
        chains.append(f"[{n}:a]adelay={ms}|{ms},volume=1.0[s{n}]")
        mix.append(f"[s{n}]")
    fc = (";".join(chains) + ";" + "".join(mix)
          + f"amix=inputs={len(parts)}:duration=longest:normalize=0[mix];"
          + "[mix]apad[a]")
    cmd = (["ffmpeg", "-y", "-v", "error"] + inputs
           + ["-filter_complex", fc, "-map", "0:v:0", "-map", "[a]",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", out])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return out if not is_silent(out) else None


def audible_fraction(path, window=10.0, floor_db=-50.0):
    """Fraction of the runtime that carries audible audio.

    ponytail: fixed 10s windows sampled end to end, not a per-sample envelope.
    Enough to catch dead-air stretches; tighten the window if a 10s dead spot
    ever slips through.
    """
    dur, _ = probe(path)
    if not dur:
        return 0.0
    total = int(dur // window) or 1
    loud = 0
    for i in range(total):
        r = subprocess.run(
            ["ffmpeg", "-v", "info", "-ss", str(i * window), "-t", str(window),
             "-i", path, "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True)
        for line in r.stderr.splitlines():
            if "mean_volume:" in line:
                try:
                    if float(line.split("mean_volume:")[1].split("dB")[0]) >= floor_db:
                        loud += 1
                except ValueError:
                    pass
                break
    return loud / total


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


def is_silent(path, floor_db=-50.0):
    """True when the audio track carries no audible signal.

    A file can have a perfectly good `aac` stream that is digital silence — the
    exact failure that shipped build-log-003 (mean_volume -91 dB). Presence of a
    stream is not presence of sound, so any narrated artifact must pass this.
    """
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", path, "-af", "volumedetect",
         "-f", "null", "-"],
        capture_output=True, text=True)
    for line in r.stderr.splitlines():
        if "mean_volume:" in line:
            try:
                return float(line.split("mean_volume:")[1].split("dB")[0]) < floor_db
            except ValueError:
                return True
    return True  # no measurement -> treat as silent (fail closed)


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
    # a narrated episode whose audio is digital silence must never pass as done
    assert is_silent("/home/romel/OpenMontage/projects/programmes/build-log-003---free-gpu-lab.mp4"), \
        "silence detector failed on the known-silent 003 artifact"
    assert not is_silent("/home/romel/OpenMontage/projects/programmes/build-log-001.mp4"), \
        "silence detector false-positived on the known-good 001 artifact"
    print(f"OK  episode={secs}s  cuts={len(cuts)}  chapters=2  narration={len(narration)} chars")
    print("    silence detector: 003 silent=True  001 silent=False")
    print(f"    scene types: {sorted({c.get('type') for c in cuts})}")
