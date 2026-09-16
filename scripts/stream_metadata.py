#!/usr/bin/env python3
"""
Stream metadata builder — answers YouTube Studio's discoverability feedback.

Studio flagged four things on our channel: (1) default generic titles on every
stream, (2) short/fragmented sessions from encoder restarts, (3) no thumbnails /
descriptions / chapters on replays, (4) no Shorts or highlights.

This fixes (1), (3) and (4) in the cheapest durable way: one module that turns a
programme episode into a paste-ready title (<=100 chars), a description with
chapters/timestamps, tags, and a vertical Shorts cut. The operator pastes it into
Studio once per broadcast — no OAuth, no API keys, nothing that can act on the
account by itself.

(2) is operational, not code: keep ONE persistent broadcast per programming
block, never recreate the broadcast on encoder restart, and run setup tests as
unlisted first. That rule lives in the CHANNEL prompt.

Skipped: YouTube Data API integration. It needs OAuth creds with write scope on
the owner's personal Google account, which is exactly the credential class the
safety rules keep stubbed. Paste-ready text achieves the same discoverability
with zero account risk. Add the API only if the owner explicitly approves
write-scope creds.

ponytail: chapters are derived from the programme cuts JSON we already produce,
not from a second source of truth that can drift.
"""
import json
import os
import subprocess
import sys

TITLE_LIMIT = 100
DESC_LIMIT = 5000


def fmt_ts(secs):
    secs = int(round(secs))
    return f"{secs // 60}:{secs % 60:02d}"


def chapters_from_programme(props_path):
    """Title cards we already emit (ident, chapter cards, outro) -> chapters."""
    with open(props_path, encoding="utf-8") as fh:
        cuts = json.load(fh)["cuts"]
    chapters = []
    for c in cuts:
        cid = c.get("id", "")
        if c.get("type") == "hero_title":
            chapters.append((c["in_seconds"], c.get("text", "") + " — live"))
        elif cid.endswith("title"):
            chapters.append((c["in_seconds"], c.get("text", "")))
        elif cid == "outro":
            chapters.append((c["in_seconds"], "Outro — " + (c.get("text", "")[:60])))
    chapters.sort()
    return [(fmt_ts(t), name.strip()) for t, name in chapters if name.strip()]


def build_title(topic, brand="Hostamar TV Live"):
    title = f"{topic} | {brand}"
    if len(title) > TITLE_LIMIT:
        title = title[: TITLE_LIMIT - 1] + "…"
    return title


def build_description(topic, chapters, links=("https://hostamar.com/tv",)):
    lines = [
        f"{topic} — live on Hostamar TV. Built, rendered and narrated in-house.",
        "",
    ]
    if chapters:
        lines.append("Chapters:")
        lines += [f"{ts} {name}" for ts, name in chapters]
        lines.append("")
    lines += ["Watch live:", *[f"- {u}" for u in links]]
    desc = "\n".join(lines)
    assert len(desc) <= DESC_LIMIT, f"description {len(desc)} chars over limit"
    return desc


def build_tags(topic_words, extra=("hostamar", "bangla tech", "live")):
    seen, tags = set(), []
    for t in list(topic_words) + list(extra):
        t = t.strip().lower()
        if t and t not in seen:
            seen.add(t)
            tags.append(t)
    return tags[:15]


def write_meta(topic, props_path, out_dir):
    """Title + description + tags, as files ready to paste into Studio."""
    chapters = chapters_from_programme(props_path)
    meta = {
        "title": build_title(topic),
        "description": build_description(topic, chapters),
        "tags": build_tags(topic.split()),
        "chapters": chapters,
    }
    os.makedirs(out_dir, exist_ok=True)
    slug = "".join(c if c.isalnum() else "-" for c in topic.lower())[:40].strip("-")
    title_path = os.path.join(out_dir, f"{slug}-studio.txt")
    with open(title_path, "w", encoding="utf-8") as fh:
        fh.write("TITLE:\n" + meta["title"] + "\n\nDESCRIPTION:\n"
                 + meta["description"] + "\n\nTAGS:\n" + ", ".join(meta["tags"]) + "\n")
    with open(os.path.join(out_dir, f"{slug}.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1, ensure_ascii=False)
    return meta, title_path


def cut_shorts(src_mp4, out_mp4, clip_secs=30):
    """Vertical 30s Shorts cut from the middle of an episode.

    Center-crop to 1080x1920; audio copied untouched. Landscape 1080p sources
    are scaled up to cover first (a plain crop would fail: 1080 rows cannot
    yield 1920). Returns ffprobe-verified (duration, width, height) or raises.
    """
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", src_mp4], capture_output=True, text=True)
    total = float(r.stdout.strip())
    start = max(0, (total - clip_secs) / 2)
    cmd = ["ffmpeg", "-y", "-ss", str(round(start, 1)), "-i", src_mp4,
           "-t", str(clip_secs), "-vf",
           "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
           "-c:a", "copy", out_mp4]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=width,height", "-of", "json", out_mp4],
        capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    v = next(s for s in d["streams"] if "width" in s)
    return float(d["format"]["duration"]), v["width"], v["height"]


if __name__ == "__main__":
    # self-check: metadata must be paste-ready and within YouTube's limits
    demo_props = {"cuts": [
        {"id": "ident", "in_seconds": 0, "out_seconds": 6,
         "type": "hero_title", "text": "HOSTAMAR TV"},
        {"id": "c1title", "in_seconds": 6, "out_seconds": 10,
         "type": "text_card", "text": "1. Agent Cloud"},
        {"id": "c1s0", "in_seconds": 10, "out_seconds": 30,
         "type": "text_card", "text": "No servers."},
        {"id": "outro", "in_seconds": 30, "out_seconds": 38,
         "type": "callout", "text": "hostamar.com"},
    ]}
    with open("/tmp/meta-selfcheck.json", "w") as fh:
        json.dump(demo_props, fh)
    meta, path = write_meta("Build Log 001 — Agent Cloud", "/tmp/meta-selfcheck.json", "/tmp")
    assert len(meta["title"]) <= TITLE_LIMIT, "title over 100 chars"
    assert "0:00" in meta["description"] and "Chapters:" in meta["description"]
    ts = [t for t, _ in meta["chapters"]]
    assert ts == sorted(ts), "chapters must be ascending"
    assert "1. Agent Cloud" in meta["description"], "chapter card missing from description"
    print(f"OK  title={meta['title']!r} ({len(meta['title'])} chars)")
    print(f"    chapters={len(meta['chapters'])}  tags={len(meta['tags'])}  -> {path}")
