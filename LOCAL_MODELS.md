# Local models — what runs on our own box (Sep 2026)

Goal: everything in-house, plus free APIs. No paid inference anywhere.

## LLM (chat / employees)

| Model | Where | Notes |
|---|---|---|
| `auto` via OmniRoute → big-pickle (opencode free) | `:20128` | What all 22 employees use. Verified: content + `stop` + tool calls, 12/12 stable. |
| NVIDIA free tier (139 models) | via OmniRoute | Fallback. Key in gateway env. |
| Qwen3.8-27B Q4_K_XL (17.6G) | `:8999` llama-server, 127.0.0.1 | Correct but ~2 t/s (dense 27B > 8GB VRAM → CPU-bound). Hermes provider `QwenLocal`. Offline fallback, not daily driver. |
| Gemma-3-4B Q4 (2.5G) | `~/.hyperspace/models/`, idle | Fast + multimodal (vision). Not served. Serve it if a local vision task appears. |
| Qwen3.8-Flash-Next NVFP4 (~124G) | `~/models/`, idle | Unusable on 8GB VRAM. Kept, not loaded. |

Tried and dropped: wiring `:8999` into OmniRoute as a `llamafile` connection —
base-URL override never reaches the outbound client (`Invalid outbound URL`),
and the combo path needs catalog ids that don't exist for local models.
The Qwen stays directly reachable; don't re-attempt without reading the
provider-node resolution code first.

## Video

HunyuanVideo stack in **`~/ComfyUI/models`** (moved off C: Sep 2026 — Windows
ComfyUI portable is gone, WSL is authoritative):

- `diffusion_models/.../hunyuan_video_720_fp8_e4m3fn.safetensors` (~13G)
- `vae/hunyuan_video_vae_bf16.safetensors`
- `LLM/llava-llama-3-8b-text-encoder-tokenizer/` (~15G)
- `clip/clip-vit-large-patch14/`

Limits (measured, REEL's lane): 384×216 max unsupervised — 512×288 froze the
box. RTX 5060 8GB is shared with the Windows host, so queue must be empty
before submitting.

## Image (thumbnails, covers, Shorts art)

`checkpoints/sd_xl_turbo_1.0_fp16.safetensors` (6.9G, byte-exact + header-verified)
in `~/ComfyUI/models`, read by the Windows origin through extra_model_paths.yaml.
SDXL-Turbo: 4 steps at 1024px in ~40s, verified first render
(projects/thumbnails/sdxl-first-proof.png — green play mark on dark, on-brief).
API note: POST /prompt through the wsl-browser-bridge fails on duplicate
Content-Type; use Windows curl.exe interop against :8189 directly (or plain
urllib without explicit Content-Type).

## Voice

| Engine | Where | Notes |
|---|---|---|
| edge-tts (free API) | default in `build_programme.narrate()` | Human voice, no key. |
| piper + lessac-medium (63M) | `~/voices/`, in-house | Offline fallback, wired into `narrate()`. Verified 5.3s / mean −16dB. Override voice via `HOSTAMAR_PIPER_VOICE`. |

## Speech-to-text

faster-whisper, local, installed. No key, no account.

## What is intentionally NOT local

- YouTube/Facebook/Cloudflare/Vercel APIs — third-party platforms by definition.
- edge-tts — free Microsoft API; piper covers offline.
