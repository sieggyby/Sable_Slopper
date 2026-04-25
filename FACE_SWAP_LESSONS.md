# Face Swap Lessons

Tracked failures, fixes, and recipes from iterating the face-swap pipeline.

The hosted path lives in `sable/face/swapper.py` (Replicate API, model fallback chain: `cdingspub/facefusion` → `yan-ops/faceswap` → `omniedge/faceswap`).

A separate operator-laptop-only path is being prepared, backed by a local FaceFusion install (`~/Projects/facefusion_install/`) and an older roop install (`~/roop-env/`). The lessons below were learned during that local-pipeline work — originally captured at `~/Desktop/fletcher_extract/wisdom.md` (a coworker has cloned the standalone scripts; the Desktop folder is the source of truth for that branch of work).

---

## TL;DR — current optimal recipe

1. **Source reference**: a sharp, near-frontal crop of the target identity, validated against a composite of all candidate frames. Curated similarity-scored picks beat random reference grabs.
2. **Target**: short clip, ideally already at decent resolution (≥720p). Higher source target = higher swap ceiling.
3. **Tool**: FaceFusion local CLI (better identity transfer than roop's bundled `inswapper_128`).
4. **Encoding**: CRF 12, libx264, yuv420p. Roop's quality flag is INVERTED — pass low values for high quality.
5. **No GFPGAN on top of swap.** It restores faces toward the underlying target geometry and visibly unwinds the identity transfer.

---

## Bug log

### 1. Wrong reference image (most damaging)
**Symptom:** Swap output looks indistinguishable from target — face still reads as the original person.
**Root cause:** A reference image with a similar filename ended up being a different person entirely (a 686×386 thumbnail pulled from an unrelated video).
**Fix:** Always validate the reference image against a composite of curated candidates before kicking off a swap. Prefer the highest-similarity frames from the candidate scoring run.

### 2. Roop's `--output-video-quality` flag is inverted
**Symptom:** Passing `--output-video-quality 90` (intuitively "high quality") produced a 295 Kbps file — same as the default 35.
**Root cause:** In `roop/utilities.py:54`:
```python
output_video_quality = (roop.globals.output_video_quality + 1) * 51 // 100
```
This maps the input `0-100` to CRF `0-51`. **Higher input → worse quality.** Mapping table:
| Flag value | CRF | Quality |
|---|---|---|
| 0  | 0  | lossless (huge files) |
| 5  | 3  | near-lossless |
| 17 | 9  | very high |
| 23 | 12 | visually transparent (recommended) |
| 35 | 18 | default — content-dependent (~300 Kbps on talking-head) |
| 90 | 46 | terrible |

**Fix:** Use `--output-video-quality 23` for CRF 12. Or bypass roop's encoder entirely and re-encode from `--keep-frames` temp PNGs with `ffmpeg -crf 12`.

### 3. GFPGAN face_enhancer reverts the swap
**Symptom:** Adding `--frame-processor face_swapper face_enhancer` made the output sharper but the swap less visible — face geometry pulled back toward the target.
**Root cause:** GFPGAN is a face *restoration* model. Its priors push toward "what a real face looks like given this geometry," and the underlying frame still has the target's bone structure, lighting, and pose. On chained swaps the restoration step amplifies target features and dampens source identity.
**Fix:** Don't run face_enhancer on swapped frames. If you want sharpening, use a non-identity-aware filter (ffmpeg `unsharp`, e.g. `-vf unsharp=5:5:0.8:3:3:0.0`). Note this also makes the GFPGAN run a waste of ~14 min wallclock.

### 4. Hosted Replicate face-swap silently no-op'd (cost: $4.12)
**Symptom:** The Replicate-backed run via `sable/face/swapper.py` produced a video visually identical to the target. The job reported `✓ Done` and was billed.
**Evidence:** Per-job log reported `Frames: 0/428` after `Done`. Output bitrate (1.89 Mbps) and pixel format (yuv444p) differed from target — the file was re-encoded — but face content was unchanged.
**Diagnosis:** The hosted swap engine returned zero successfully-swapped frames. This should never bill as a successful run.
**Fix:** Don't trust a "Done" message. Always perceptually diff a sample frame between target and swap output before paying. Quick check:
```bash
ffmpeg -ss N -i target -frames:v 1 a.jpg && ffmpeg -ss N -i swap -frames:v 1 b.jpg
```
TODO: add a frame-diff guard inside `sable/face/swapper.py` before logging Replicate cost — refuse to count the run as successful if the output is byte-identical-ish to the target.

### 5. Multi-thread roop crash on temp PNG read
**Symptom:** `AttributeError: 'NoneType' object has no attribute 'shape'` partway through face_swapper or face_enhancer.
**Root cause:** Under high memory pressure (10+ GB process RSS, 97% full disk → tight swap space), `cv2.imread` intermittently returns `None` for valid temp PNGs. Re-running `imread` on the same file moments later succeeds. The bug is in the OS/cv2 interaction, not the file.
**Fix:** Wrap reads with retry logic. The pattern from `finish_enhance.py` lines 28-34 in the standalone scripts works (3 attempts, 0.5s sleep). Even with `--execution-threads 1` the bug recurs, so it's not strictly a thread race — it's I/O pressure.

### 6. Multi-process frame ordering ≠ progress %
**Symptom:** Roop crashes at "frame 335/428" but only ~334 frames have updated mtimes from the enhancer pass. The remaining 94 are scattered across the timeline (40, 41, 42, ..., 331, 334, 335, 336, 337), not contiguous.
**Cause:** `multi_process_frame` distributes work across the thread pool. The progress counter increments by completed-count, not by frame index.
**Implication:** When a roop run crashes mid-stream, you can salvage partial work. Compare temp PNG mtimes against the swapper-stage mtime range — frames written *after* the swapper completed are already enhanced. Run only the unenhanced subset to finish.

---

## Performance numbers (Apple Silicon, CoreML)

| Stage | Throughput | Notes |
|---|---|---|
| Frame extraction (ffmpeg) | ~430 frames in 2 sec | Trivial |
| Roop face_swapper (multi-thread) | ~1.6 frames/sec | inswapper_128.onnx |
| Roop face_swapper (single-thread) | ~1.1-1.4 frames/sec | Marginal slowdown — CoreML doesn't parallelize much |
| Roop face_enhancer (multi-thread) | ~0.5 frames/sec | GFPGAN, ~10 GB RSS |
| Roop face_enhancer (single-thread) | ~0.45 frames/sec | Same RSS, slightly slower wallclock |
| Standalone enhancer via `finish_enhance.py` | ~0.5 frames/sec | Includes per-frame face detection |

**Wallclock estimates for a 14-second clip (428 frames):**
- Swap only: ~5 min
- Swap + GFPGAN: ~20 min
- Encode + audio restore: < 30 sec

These wallclocks are why the local pipeline is operator-laptop-only — too slow and too RAM-hungry to run on the Hetzner VPS that hosts `sable serve` and the weekly automation.

---

## FaceFusion local CLI

Installed at `~/Projects/facefusion_install/`. Activate via:
```
~/Projects/facefusion_install/venv/bin/python ~/Projects/facefusion_install/facefusion.py headless-run …
```

### Why it's preferred over roop
- **Stronger swap models**: `hyperswap_1a/1b/1c_256`, `ghost_1/2/3_256`, `simswap_unofficial_512`, `hififace_unofficial_256` (vs roop only having `inswapper_128`).
- **Identity-preserving enhancers**: `codeformer`, `gpen_bfr_*`, `restoreformer_plus_plus` — plus `--face-enhancer-blend` (0-100) and `--face-enhancer-weight` (0.0-1.0) so you can apply enhancement *partially* without fully reverting the swap.
- **Pixel boost during swap**: `--face-swapper-pixel-boost 512x512` (or 768/1024) renders the swap at higher resolution before merging back — fixes the "blurry swap" look common at 128 px.
- **Hardware encoder**: `h264_videotoolbox` for fast Apple Silicon encode.
- **Face occlusion** (`--face-occluder-model xseg_3`) handles hair/hands/glasses crossing the face better than roop.
- **Reference face distance** (`--reference-face-distance`) lets you tune match strictness if multiple faces are in frame.

### Recommended starting recipe (Apple Silicon)
```
~/Projects/facefusion_install/venv/bin/python ~/Projects/facefusion_install/facefusion.py headless-run \
  --execution-providers coreml \
  --processors face_swapper \
  --face-swapper-model hyperswap_1c_256 \
  --face-swapper-pixel-boost 512x512 \
  --face-detector-model retinaface \
  --face-occluder-model xseg_3 \
  --face-selector-mode reference \
  --output-video-encoder h264_videotoolbox \
  --output-video-quality 95 \
  -s <SOURCE_FACE.png> \
  -t <TARGET.mp4> \
  -o <OUTPUT.mp4>
```

If face needs sharpening *and* identity preservation:
```
  --processors face_swapper face_enhancer \
  --face-enhancer-model codeformer \
  --face-enhancer-weight 0.4 \
  --face-enhancer-blend 50
```
(Lower weight + blend = enhancer touches the swap less, identity preserved better than the GFPGAN-1.4 default.)

---

## Reference-frame extraction pipeline

The standalone scripts in `~/Desktop/fletcher_extract/` (and the coworker's clone) implement a four-stage candidate extraction flow that produced the highest-quality reference frames:

1. `extract_face.py` — pull face crops from a source video at 1 fps.
2. `build_faceset.py` — assemble a candidate set from the crops.
3. `filter_by_reference.py` — score candidates by embedding similarity to a single seed reference.
4. `add_closed_mouth.py` — secondary scoring pass for closed-mouth picks (better for some target shots).

The output naming convention `top01_t<frame>s_sim<score>_*.png` makes the highest-similarity picks self-identifying. A `_composite.png` is generated for visual sanity-check before any expensive swap run.

When this work gets folded into a future `sable face local` subcommand, this four-stage flow is the reference-prep half of the pipeline; the FaceFusion recipe above is the swap half.

---

## Open questions / next experiments

- [ ] FaceFusion `hyperswap_1c_256` + pixel boost vs roop `inswapper_128` on the same target — does identity transfer get measurably stronger?
- [ ] Codeformer at weight 0.4 — does it sharpen without reverting identity?
- [ ] Add a perceptual-diff guard inside `sable/face/swapper.py` — refuse to count a Replicate run as successful (and log cost) if the output is effectively a re-encode of the target.
- [ ] Decide whether `sable face local` is its own subcommand or a `--backend=local` flag on the existing `sable face` command.
