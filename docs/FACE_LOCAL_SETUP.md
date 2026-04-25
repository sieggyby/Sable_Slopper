# `sable face local` — Setup & Walkthrough

End-to-end install and usage guide for the operator-laptop-only face-swap pipeline.

This is **separate from the hosted `sable face swap` path** (which uses Replicate and runs from the VPS). The local path runs FaceFusion on Apple Silicon / CoreML, takes 5–20 min wallclock per clip, and uses ~10 GB RSS — it is intended for an operator's laptop, not the VPS.

If you hit unexpected behavior, read [`FACE_SWAP_LESSONS.md`](../FACE_SWAP_LESSONS.md) — it documents the failure modes we already paid for.

---

## Assumptions

- macOS on Apple Silicon (M1/M2/M3+). Linux + CUDA may work but is untested.
- Homebrew installed.
- `git` and `python3` available.
- ~30 GB free disk for FaceFusion model downloads.

If you are on a different platform, follow the FaceFusion docs for your platform and adjust the `--execution-providers` flag in `sable/face/local/swap.py` (`SwapParams.execution_providers`). Everything else is platform-agnostic.

---

## Step 1 — Clone Sable_Slopper and install

```bash
git clone https://github.com/<your-org>/Sable_Slopper.git ~/Projects/Sable_Slopper
cd ~/Projects/Sable_Slopper

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[face-local]"
```

The `[face-local]` extra pulls in: `insightface`, `opencv-python`, `scikit-image`, `numpy`, `yt-dlp`, `onnxruntime`. These are only needed on the operator's laptop — the VPS runs without them.

Verify:

```bash
sable face local --help
```

Expected output starts with `Usage: sable face local [OPTIONS] COMMAND [ARGS]...` and lists subcommands `closed`, `extract`, `faceset`, `filter`, `preflight`, `salvage`, `swap`.

---

## Step 2 — Install ffmpeg

```bash
brew install ffmpeg
```

Verify: `ffmpeg -version` and `ffprobe -version` both print version info.

---

## Step 3 — Install FaceFusion (separate venv)

FaceFusion is heavy (PyTorch + ONNX models) and must be in its own environment so it doesn't fight with Sable's deps.

```bash
mkdir -p ~/Projects && cd ~/Projects
git clone https://github.com/facefusion/facefusion.git facefusion_install
cd facefusion_install
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
python install.py --onnxruntime coreml-silicon
```

Smoke check FaceFusion itself:

```bash
~/Projects/facefusion_install/venv/bin/python ~/Projects/facefusion_install/facefusion.py --version
```

Expected: prints a FaceFusion version string and exits 0.

If you installed FaceFusion somewhere else, tell Sable about it (one of these):

```bash
# Option A — sable config
sable config set face_local.facefusion_path /path/to/facefusion_install

# Option B — env var (good for one-off testing)
export SABLE_FACEFUSION_PATH=/path/to/facefusion_install

# Option C — per-command override
sable face local swap ... --facefusion-path /path/to/facefusion_install
```

The default lookup is `~/Projects/facefusion_install/`.

---

## Step 4 — (Optional) Install roop for the salvage helper

Only needed if you want to use `sable face local salvage` to recover from a crashed roop run. The hosted `sable face swap` path doesn't use roop, and a fresh local pipeline started today can use FaceFusion exclusively.

```bash
cd ~
python3 -m venv roop-env
source roop-env/bin/activate
git clone https://github.com/s0md3v/roop.git ~/roop-env/roop
cd ~/roop-env/roop
pip install -r requirements.txt
```

Tell Sable where roop lives if you put it elsewhere:

```bash
sable config set face_local.roop_path /path/to/roop-env/roop
# or
export SABLE_ROOP_PATH=/path/to/roop-env/roop
```

Default: `~/roop-env/roop`.

---

## Step 5 — Run preflight

```bash
sable face local preflight
```

You should see a green ✓ next to every check:

| Check | What it verifies |
|---|---|
| `ffmpeg`, `ffprobe` | On PATH |
| `cv2`, `numpy`, `insightface`, `skimage` | Import cleanly |
| `facefusion_root` | Directory exists |
| `facefusion_venv_python` | `<facefusion>/venv/bin/python` exists |
| `facefusion_entry` | `<facefusion>/facefusion.py` exists |
| `facefusion_smoke` | `facefusion --version` returns 0 |

If any check fails, the command exits 1 and prints what's wrong. Fix the failing piece before continuing.

---

## End-to-end walkthrough — swap a face into a video

We'll take a YouTube interview, find the best frames of someone, register that as a reference identity, then swap their face onto a target video.

### Stage A — pull candidate frames out of a source video

```bash
sable face local extract \
  "https://www.youtube.com/watch?v=YOUR_SOURCE_INTERVIEW" \
  --account @some_handle \
  --top 12
```

Output goes to `~/sable-workspace/face_local/@some_handle/<video_slug>/headshots/top*.png`. Filenames embed score, sharpness, det_score, and frontality — pick the cleanest near-frontal shot as your seed reference.

A common gotcha: the source video has more than one face in it. The extract step picks the highest-scoring faces *regardless of identity*, so you may get a mix. That's what stage B is for.

### Stage B — identity-filter against your seed reference

Pick one image from the headshots (e.g. `top04_t0428s_score920_sharp...png`) and use it as the reference:

```bash
sable face local filter \
  "https://www.youtube.com/watch?v=YOUR_SOURCE_INTERVIEW" \
  --account @some_handle \
  --reference ~/sable-workspace/face_local/@some_handle/<slug>/headshots/top04_*.png \
  --threshold 0.45 \
  --top 15
```

Output: `<workspace>/matches/top*.png`. Threshold 0.45 is the ArcFace "same person" line; lower if you don't get enough hits, raise to be stricter.

**Always sanity-check by opening the resulting `matches/` folder before continuing.** The first time we ran this on a real video, we used the wrong reference image entirely — see [`FACE_SWAP_LESSONS.md` bug #1](../FACE_SWAP_LESSONS.md).

### Stage C — (optional) closed-mouth subset

If your target video has the subject mostly closed-mouth, run:

```bash
sable face local closed \
  "https://www.youtube.com/watch?v=YOUR_SOURCE_INTERVIEW" \
  --account @some_handle \
  --reference <same reference path as above>
```

This adds `closed_top*.png` files alongside the existing `top*.png` matches. Open mouths in references can make a swap look uncanny.

### Stage D — build a curated faceset (optional)

```bash
sable face local faceset \
  --account @some_handle \
  --slug <video_slug> \
  --source matches \
  --curate-n 6
```

Outputs:
- `<workspace>/curated/c01_*.png` ... `c06_*.png` — diversity-curated subset (greedy farthest-point in embedding space).
- `<workspace>/embedding.npy` — score-weighted average ArcFace identity vector.
- `<workspace>/composite.png` — landmark-aligned pixel mean. **Do not use this as a swap source** — it's a visual sanity-check only.

### Stage E — register the reference in the face library

Pick the single best reference (highest `sim`, sharp, frontal) and register it. This is the *same* library that the hosted `sable face swap` path reads from.

```bash
sable face library add \
  ~/sable-workspace/face_local/@some_handle/<slug>/curated/c01_*.png \
  --name some_handle --consent
```

`--consent` is required: only run face swaps on individuals who have consented.

### Stage F — run the swap

```bash
sable face local swap \
  ~/.sable/face_library/c01_*.png \
  ~/Downloads/target_clip.mp4 \
  -o ~/Desktop/swapped.mp4
```

This uses the recipe from `FACE_SWAP_LESSONS.md`: `hyperswap_1c_256` + 512×512 pixel boost + retinaface + xseg_3 occluder + h264_videotoolbox + CRF 12.

For a 14-second clip, expect ~5 minutes wallclock. The output sidecar at `swapped.mp4_meta.json` records the recipe and elapsed time.

If the result is sharp but identity is weak, try adding the enhancer at low weight:

```bash
sable face local swap source.png target.mp4 -o out.mp4 \
  --enhance --enhancer-model codeformer --enhancer-weight 0.4 --enhancer-blend 50
```

**Do not** stack GFPGAN — it reverts the swap (see `FACE_SWAP_LESSONS.md` bug #3).

### Verify

```bash
ffmpeg -ss 5 -i ~/Downloads/target_clip.mp4 -frames:v 1 /tmp/before.jpg
ffmpeg -ss 5 -i ~/Desktop/swapped.mp4 -frames:v 1 /tmp/after.jpg
open /tmp/before.jpg /tmp/after.jpg
```

If `after.jpg` looks identical to `before.jpg`, the swap silently no-op'd — see `FACE_SWAP_LESSONS.md` bug #4. Re-check your source reference and the FaceFusion log at `<output>_facefusion.log`.

---

## Reference: directory layout

After a full pipeline run for one video, the workspace looks like:

```
~/sable-workspace/face_local/@some_handle/<video_slug>/
├── samples/                        # 1080p sample frames (ffmpeg)
│   └── f_00001.jpg ... f_NNNNN.jpg
├── headshots/                      # extract output
│   └── top01_t0042s_score....png ... top12_*.png
├── matches/                        # filter + closed output
│   ├── top01_t0428s_sim0.71_*.png
│   └── closed_top01_*.png
├── curated/                        # faceset diversity subset
│   └── c01_*.png ... c06_*.png
├── candidates.pkl                  # detection cache (re-run filter quickly)
├── embedding.npy                   # averaged identity vector
└── composite.png                   # visual sanity check (do NOT swap from this)
```

The face library is separate, at `~/.sable/face_library/` — that's where registered reference images live and where both `sable face swap` and `sable face local swap` read from.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `preflight` fails on `cv2` / `insightface` | `[face-local]` extra not installed | `pip install -e ".[face-local]"` |
| `preflight` fails on `facefusion_smoke` | Wrong path or broken venv | `sable config set face_local.facefusion_path …` and reinstall FF venv |
| `extract` finds no faces | `--detect-h` too low or `--min-face-frac` too strict | Try `--detect-h 1440 --min-face-frac 0.05` |
| `filter` returns no matches | Reference image is wrong person | Validate against `composite.png` from a `faceset` run; see lessons bug #1 |
| Output video looks identical to target | Silent no-op (or wrong reference) | Perceptually diff a frame; check FF log; see lessons bug #4 |
| `swap` is sharper than target but face geometry pulled back | GFPGAN/restorer overrode the swap | Drop `--enhance` or lower `--enhancer-weight` to 0.2; see lessons bug #3 |
| Roop crashed mid-stream with `'NoneType' has no attribute 'shape'` | I/O pressure on temp PNGs | Use `sable face local salvage` to finish; see lessons bug #5 |
| `sable face local swap --output-video-quality 90` produces low quality | Roop's quality flag is inverted (does not apply to FaceFusion) | If using roop, pass low values for high quality; see lessons bug #2 |

If you're stuck, read `FACE_SWAP_LESSONS.md` end-to-end before re-running anything expensive.

---

## Notes for Codex (or any AI pair-programmer working in this repo)

If you're using Codex / Claude Code / Cursor to extend or debug this pipeline:

1. **Start by reading these in order:**
   - `FACE_SWAP_LESSONS.md` (root) — what we already know breaks.
   - `sable/face/local/__init__.py` — module docstring with the boundary.
   - `sable/face/local/cli.py` — CLI surface.
   - `sable/face/local/swap.py` — the FaceFusion shell-out (note the `SwapParams` defaults match the lessons recipe).
2. **The hosted path is `sable/face/swapper.py`** — Replicate-backed, runs from the VPS, uses `cdingspub/facefusion`/`yan-ops`/`omniedge` model fallback. Do not conflate the two.
3. **Heavy imports are deferred** inside function bodies on purpose — `sable face local --help` must work on a fresh clone before the `[face-local]` extras are installed. Don't hoist imports to module top without re-checking the smoke tests at `tests/face/test_local_cli.py`.
4. **No new top-level dependencies** without justification (see `CLAUDE.md` working conventions). New ML-pipeline deps belong under `[face-local]` in `pyproject.toml`.
5. **Tests:** the smoke tests at `tests/face/test_local_cli.py` run without ML dependencies installed. They are the floor for "did I break the CLI surface?". If you add a new subcommand, add a smoke assertion there.
6. **Workspace paths** go through `sable.shared.paths.face_local_workspace(handle, slug)` — don't hardcode anywhere.
7. **YouTube URLs are accepted** anywhere a video path is — `sable.shared.download.maybe_download` handles both. Do not duplicate yt-dlp invocations.
