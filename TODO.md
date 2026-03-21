# TODO

## score_brainrot.py — Automatic Brainrot Library Populator

- [x] Implement `scripts/score_brainrot.py`
  - [x] Audio energy signal via librosa (weight 0.55)
  - [x] Motion density signal via OpenCV at 2fps (weight 0.45)
  - [x] Graceful fallback: no audio → motion-only; no OpenCV → audio-only
  - [x] Combined signal with 3s rolling smooth
  - [x] Need-score calculation from existing library
  - [x] Per-tier window scoring with quality percentile threshold
  - [x] Greedy non-overlapping window selection
  - [x] Energy classification (high / medium / low)
  - [x] Collision-safe output naming (_v2, _v3...)
  - [x] `--dry-run` support with plan table
  - [x] Register clips via `add_video()`
- [x] Add `score` optional dep group to `pyproject.toml` (librosa, opencv-python, numpy)
- [x] Document `score_brainrot.py` in `README.md`

## `--clip-only` Mode — Clip Without Brainrot

**Status:** `--no-brainrot` flag exists but is broken (passes `energy="none"` to `pick_brainrot()`,
which raises RuntimeError when no matching videos are found).

**Planned behavior:**
When `--no-brainrot` is passed:
1. Extract source clip segment (same as current)
2. Skip brainrot selection and looping entirely
3. Scale source clip to full 9:16 portrait (no split — source takes full frame)
4. Burn ASS captions on full frame
5. Encode with same platform profile

**Implementation notes:**
- Fix `assemble_clip()` in `assembler.py`: check `brainrot_energy == "none"` or add `clip_only: bool` param
- Add `stack_videos_clip_only()` to `ffmpeg.py` (or modify `stack_videos` to accept `top_path=None`):
  - Filter: `[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}[out]`
  - Audio: interview audio with loudnorm (same as brainrot mode)
- Captions burn on full frame (adjust PlayResY to full height, not split)
- Hook overlay same as brainrot mode
- Output naming: `clip_01_cliponly.mp4` or same name under different subfolder
