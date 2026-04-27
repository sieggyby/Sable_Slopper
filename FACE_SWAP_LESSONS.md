# Face Swap Lessons

Tracked failures, fixes, and recipes from iterating the face-swap pipeline.

The hosted path lives in `sable/face/swapper.py` (Replicate API, model fallback chain: `cdingspub/facefusion` → `yan-ops/faceswap` → `omniedge/faceswap`).

A separate operator-laptop-only path is being prepared, backed by a local FaceFusion install (`~/Projects/facefusion_install/`) and an older roop install (`~/roop-env/`). The lessons below were learned during that local-pipeline work — originally captured at `~/Desktop/fletcher_extract/wisdom.md` (a coworker has cloned the standalone scripts; the Desktop folder is the source of truth for that branch of work).

---

## TL;DR — current optimal recipe

1. **Source**: 2-3 reference photos at different angles passed via `-s photo1 photo2 photo3`. Web-sourced professional shots are often the strongest primary; supplement with curated 3/4-view picks from a reference-frame extraction run.
2. **Target**: short clip with the desired character on screen at the reference frame. Trim out hard moments (head turns, occlusions, scene cuts to other characters) rather than fight detection.
3. **Tool**: FaceFusion local CLI. Use `hififace_unofficial_256` for hard identity gaps, `hyperswap_1c_256` for easy ones.
4. **Always** pass `--reference-frame-number N` on multi-face clips (default frame-0 anchoring is brittle).
5. **Layer codeformer enhancer at low blend** (`--face-enhancer-blend 30 --face-enhancer-weight 0.4`) — sharpens without GFPGAN's identity-reversion problem. Often substitutes for one or two recursive passes.
6. **Encoding**: `--output-video-encoder h264_videotoolbox --output-video-quality 95` on Apple Silicon. Roop's `--output-video-quality` flag is INVERTED — pass low values for high quality.
7. **Recursive swap** amplifies identity. Sweet spot is 2x; 3x starts to soften texture. With codeformer in the stack, 1x is often enough.

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

### 7. Multi-face clips need explicit `--reference-frame-number`
**Symptom:** Swap applied to the wrong character. In a Denzel/Ethan car-scene clip, FaceFusion silently picked frame 0's face (Ethan) as the reference and swapped Ethan, leaving Denzel untouched.
**Root cause:** `--face-selector-mode reference` defaults to frame 0 for the reference face when no `--reference-frame-number` is specified. If your intended target isn't on screen at t=0, the wrong face is anchored for the entire run.
**Fix:** Always pass `--reference-frame-number N` to a frame where the intended target is in clean close-up. Verify with `ffmpeg -ss T -frames:v 1 _check.png` before launching the swap.
**Implication for `sable face local`:** The CLI should accept a `--reference-frame N` (or `--reference-time T`) flag and warn loudly if multiple faces are detected in the target without it.

### 8. Roop's `inswapper_128` is too weak for large identity gaps
**Observation:** Swapping a 30s/40s subject onto a 70s subject (Fletcher → Powell DJ meme) with roop produced nearly invisible identity transfer even with a correct, high-quality reference.
**Diagnosis:** `inswapper_128` is the only swapper roop ships with. Its embedding-transfer strength is low compared to newer architectures.
**Fix:** Default to FaceFusion. Within FaceFusion, on stubborn gaps use `hififace_unofficial_256` (visibly stronger identity push than `hyperswap_1c_256` and the others). For easier cases `hyperswap_1c_256 + pixel_boost 512` is faster and equivalent.
**Empirical ranking on hard identity gaps (from this iteration):**
1. `hififace_unofficial_256` — strongest identity transfer
2. `hyperswap_1c_256 + pixel_boost 768` — close second, sharper detail
3. `simswap_unofficial_512` — native 512 output, often visually similar to hyperswap
4. roop `inswapper_128` — weakest, baseline only

### 9. Recursive swap amplifies identity transfer
**Observation:** Feeding a swap output back as a target and re-running with the same source produces a progressively stronger identity push. 1x → 2x → 3x on hififace showed clearly stepped progression. 3x is the sweet spot for short clips; beyond that, hair/hat textures start to soften.
**Mechanism:** The face the swapper sees on each pass is already partially the source identity, so the embedding match strengthens.
**Caveat:** Recursion cannot fix frames that *failed* to swap on pass 1 (detection failures). Those frames stay as the original target through every recursion. Solve detection first, then recurse.
**Cost:** Linear in pass count (~30-60s per pass on a short Denzel clip).

### 10. Multi-source covers off-angle frames
**Recipe:** Pass 2-3 reference photos at different head poses via `-s frontal.png three_quarter.png down_tilt.png`. FaceFusion blends embeddings across sources; the model gets identity information from a wider pose distribution.
**When it matters:** Targets that include profile or 3/4 angle shots, where a single near-frontal source produces weak swaps on the off-angle frames.

### 11. Detector tuning catches turned heads
**Levers** (in `--face-detector-*`):
- `--face-detector-score 0.3` (default ~0.5) lowers the confidence threshold so partial-profile faces are still detected.
- `--face-detector-angles 0 90 270` re-detects after frame rotation; catches tilted heads.
- `--face-detector-model many` fuses retinaface + scrfd + yolo + yunet — strongest detection coverage.
**Trade-off:** ~3-4× slower per frame.

### 12. Pixel boost 768 sharpens face detail
**Observation:** `--face-swapper-pixel-boost 768x768` (vs default 512) visibly sharpens face detail on close-ups. `1024x1024` is available for hero shots; use sparingly — slower and disk-heavy.

### 13. Codeformer enhancer at low blend preserves identity
**Recipe:**
```
--processors face_swapper face_enhancer
--face-enhancer-model codeformer
--face-enhancer-blend 30
--face-enhancer-weight 0.4
```
Sharpens face texture without the identity-reversion problem GFPGAN has (see #3). Default GFPGAN-1.4 with full blend reverts identity; codeformer at low blend does not.

### 14. Trim before head-turn to avoid detection failure
**Pragmatic fix:** When a target clip has both clean and difficult moments (profile shots, occlusions, scene cuts), trimming to the clean window is faster than fighting detection on the difficult window. Especially true for reaction-gif use cases where only a smile or laugh moment is needed.

### 15. CoreML cannot run two FaceFusion swaps concurrently
**Symptom:** Two `facefusion.py headless-run` processes started simultaneously crash mid-job with:
```
onnxruntime.capi.onnxruntime_pybind11_state.Fail: [ONNXRuntimeError] : 1 : FAIL :
... CoreMLExecutionProvider ... Status Message: Error executing model:
Unable to compute the prediction using a neural network model. (error code: -1)
```
**Cause:** The Apple Neural Engine / CoreML execution provider doesn't multiplex two onnxruntime sessions cleanly. The second-arriving job aborts mid-frame.
**Fix:** Always run swaps sequentially on Apple Silicon. Chain with `&&` in shell scripts; do not background two facefusion runs in parallel.
**Implication for `sable face local`:** The CLI/queue must enforce serial execution per machine (a process-level lock or a single worker queue). If batch parallelism is needed, distribute across separate machines.

### 16. Visible mask artifact on recursive swaps with pixel_boost 768
**Symptom:** A subtle darker rectangular patch in the lower-face region, visible on 1x recursive and more pronounced on 2x. Looks like a translucent box ghost — mask edges showing luminance mismatch with surrounding skin.
**Cause:** With `--face-swapper-pixel-boost 768x768` and recursive passes, slight luminance offset between the boosted face render and surrounding frame compounds across each pass. Mask edges become visible as a tonal seam.
**Fix:** Increase `--face-mask-blur` (default ~0.3 → try 0.5-0.7 for softer edges). Or drop the pixel boost to 512 on recursive passes (single 768 pass + recursive 512 keeps sharpness while improving blend).

### 17. AI-modified or partially-occluded targets need the "clean recipe"
**Symptom:** The same dark-patch artifact (#16) appears on a SINGLE pass — not just recursive — when the target has been pre-processed by another AI model OR when the face is partially occluded in frame.
**Confirmed cases:**
- Microsoft commercial: face partly behind a monitor → patch on cheek/jaw.
- Runway-deglassed Powell footage: glasses removed by Runway's inpainting → patch on chin/lower face.
- Likely any Topaz upscale, GFPGAN restoration, or other AI-modified target.
**Cause:** `codeformer + xseg_3 + pixel_boost 768` overshoots when the underlying face area carries inconsistencies from prior model output. The merge mask edges become visible.
**Fix — the "clean recipe"**:
```
--processors face_swapper                # drop face_enhancer entirely
--face-swapper-model hififace_unofficial_256
--face-swapper-pixel-boost 512x512       # not 768
--face-mask-types box                    # box-only, drop xseg occluder
--face-mask-blur 0.6
--face-detector-model retinaface --face-detector-score 0.3
--face-detector-angles 0 90 270
```
Identity transfer is slightly weaker than the full hard-target recipe, but the blend is clean.

**Heuristic:** if the target has been touched by Runway / Topaz / GFPGAN / any other AI model, switch to the clean recipe. The fancy stack is for unmodified raw video only.

**Implication for `sable face local`:** the CLI should accept a `--target-modified` flag (or auto-detect via metadata) that switches to the clean recipe.

---

## Out of scope (use other tools)

FaceFusion swaps face *identity*, not accessories or hair. If a target has glasses or hair you want to change, that's a separate pipeline:

- **Glasses removal**: Runway's "Remove from video" feature works well in practice. Note its inpaint can lean toward the original target identity in the eye area, partially undoing a downstream face-swap unless you rerun the swap on the deglassed output. Replicate `lucataco/glasses-removal` is the equivalent hosted option.

- **Hair color/change**: HairFastGAN, Barbershop, or SD-based hair transfer — cloud only, large models. **A naive local approach (mask hair region above face bbox + HSV hue shift) was tested and is not viable** — even with EMA bbox smoothing and soft Gaussian masks, the per-frame approximate mask leaks onto skin/temples and the result looks synthetic. For polish, go cloud or use a real hair-segmentation model (MODNet, BiSeNet).

Workflow when needed:
1. Glasses/hair tool first (the AI-modified output is now your new target).
2. Facefusion swap with the **clean recipe** (#17 — codeformer interacts badly with AI-pre-processed pixels).
3. ffmpeg `unsharp=5:5:1.2:5:5:0.0` post-encode to recover sharpness without re-introducing identity-clashing enhancers.

This is the pipeline that produced the final deglassed-Powell-DJ deliverable.

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

### Recommended starting recipe (Apple Silicon, easy targets)
```
~/Projects/facefusion_install/venv/bin/python ~/Projects/facefusion_install/facefusion.py headless-run \
  --execution-providers coreml \
  --processors face_swapper \
  --face-swapper-model hyperswap_1c_256 \
  --face-swapper-pixel-boost 512x512 \
  --face-detector-model retinaface \
  --face-occluder-model xseg_3 \
  --face-selector-mode reference \
  --reference-frame-number <N> \
  --output-video-encoder h264_videotoolbox \
  --output-video-quality 95 \
  -s <SOURCE_FACE.png> \
  -t <TARGET.mp4> \
  -o <OUTPUT.mp4>
```

### Hard-target recipe (large identity gap, multi-face clip, off-angle moments)
```
  --face-swapper-model hififace_unofficial_256 \
  --face-swapper-pixel-boost 768x768 \
  --face-detector-score 0.3 \
  --face-detector-angles 0 90 270 \
  --face-selector-mode reference --reference-frame-number <N> \
  -s <frontal.png> <three_quarter.png> <down_tilt.png>
```
Then run the output back through the same command (recursive) 1-2 more times for stronger identity transfer.

### Sharpening recipe (preserves identity, vs GFPGAN which reverts)
```
  --processors face_swapper face_enhancer \
  --face-enhancer-model codeformer \
  --face-enhancer-blend 30 \
  --face-enhancer-weight 0.4
```
Lower weight + blend = enhancer touches the swap less, identity preserved better than the GFPGAN-1.4 default.

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

## Per-target quality verdicts

| Target | Identity gap | Best local recipe so far | Outcome |
|---|---|---|---|
| Powell DJ meme | Huge (~30 yr age, hair, glasses) | hififace + 3x recursive + multi-source | Visible drift, still reads as Powell. Local cap. |
| Denzel "my n*gga" car scene (full 4s) | Moderate | hififace + reference-frame-anchored + multi-source + detector-angles + 3x recursive | Strong on frontal frames, dropouts on profile head-turn |
| Denzel "my n*gga" smile-only trim | Moderate | hififace + multi-source + Denzel-anchored ref + pixel_boost 768 + codeformer enhancer (blend 30 / weight 0.4) + detector-score 0.3 with angles 0/90/270, single pass | ✅ Strong identity, smile preserved, no artifacts. Shipped as a reaction GIF for TIG account. |

## Compositing notes (post-swap)

When stitching the final reaction asset (caption + freeze frame + overlay), a few patterns from this iteration:

- **Eye keypoints for overlay alignment**: use insightface (`app.get(img)[0].kps`) to find exact eye coordinates rather than estimating from a thumbnail. Required for placing meme overlays like "deal with it" sunglasses on a freeze frame.
- **Caption with Impact font**: `drawtext=fontfile='/System/Library/Fonts/Supplemental/Impact.ttf':fontsize=80:fontcolor=white:bordercolor=black:borderw=5` — the heavy `borderw` is what gives meme captions their punch.
- **Freeze frame** + audio padding: `[v]tpad=stop_mode=clone:stop_duration=N` extends video by N seconds (clones last frame); combine with `-af apad=pad_dur=N -shortest` to extend audio.
- **Animated overlay drop-in**: `overlay=y='if(between(t,A,B),START+(t-A)*VEL,if(gte(t,B),END,-100))'` — sunglasses fall from above into final position.
- **Transparent PNGs from openclipart.org** use the `tRNS` chunk for alpha. They render as white in some preview tools but `ffprobe -show_entries stream=pix_fmt` confirms `pal8` (palette + transparency). Do **not** `colorkey` these — it will eat the actual sunglasses pixels (they're partially-transparent black, not fully-opaque).
- **High-quality GIF**: two-pass with palettegen — `fps=20,scale=600:-1:flags=lanczos,palettegen=stats_mode=diff` then `paletteuse=dither=bayer:bayer_scale=5`. 600px wide @ 20fps yields ~3-4 MB GIFs.

## Post-mortem: DeepFaceLab on RunPod (Fletcher → Paul Rudd Microsoft video, 2026-04-26 / 27)

The "full DeepFaceLab fine-tune" path mentioned as gold-standard in the open questions above was actually attempted. **Verdict: works, but not a clear win over local FaceFusion for the cost-and-time it takes.** Recording the receipts so we don't re-relearn this.

### Setup we ran

- **GPU rental**: RunPod, RTX A6000 (48 GB VRAM) on Community Cloud at $0.49/hr On-Demand.
- **Pod template**: `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04` (PyTorch base). Skipped community DFL templates — they're stale.
- **Storage**: 50 GB container disk + 100 GB Volume disk (lost on terminate; for archival use Network Volume next time, $0.07/GB/mo and survives termination).
- **Toolchain**: `nagadit/DeepFaceLab_Linux` wrappers + `iperov/DeepFaceLab` core, in a Python 3.11 venv with TF 2.15 + opencv 4.11 + insightface (for filtering) — though insightface broke things and we removed it.
- **Source data**: ~2,200 sampled frames + ~25 curated headshots + 4 web-sourced photos of the target identity (Fletcher) — borrowed from the existing `~/Desktop/fletcher_extract/` pipeline output. Fed straight into DFL's S3FD extractor.
- **Destination data**: 121-sec source video of the target (Paul Rudd in the Microsoft commercial) sampled at 5 fps → ~600 frames → ~500 aligned faces.

### What we actually built (two rounds)

| Round | Resolution / face_type | Iter | Wallclock | Cost | Final loss (src/dst) |
|---|---|---|---|---|---|
| **v1** | 256 / whole_face | 100,000 | ~6.5h | ~$3.30 | 0.26 / 0.25 |
| **v3** | 384 / head | 100,000 | ~15.5h | ~$7.60 | 0.18 / 0.25 |

(Round 2 was a remerge of v1 with different mask/super-res settings — same model, no retrain.)

Total spend across both rounds + setup debugging: **~$13**. Within budget but more than the "$5–10 per voice" framing the path was sold under.

### What actually came out

Both videos shipped to `~/Desktop/fletcher_as_rudd*.mp4`. Operator review of v3 (the better one):

- **Identity reads as Fletcher** — yes, the swap is recognizable. Better than FaceFusion's `hyperswap_1c_256` on this particular target.
- **Forehead inclusion**: fixed in v3 by retraining with `--face-type head` instead of `whole_face`. v1 left Paul Rudd's forehead through, v3 doesn't.
- **Resolution gap**: trained at 384 but composited into a 1080p frame, so the swap region is still visibly softer than the surrounding video. Super-resolution at merge time (`--super-resolution-power 100`) helps but doesn't close the gap.
- **Mask shimmering**: still present in v3 — frame-to-frame mask edge instability. Softer mask blur (`--blur-mask-modifier 70`) and negative erosion (`-40`, expands mask up to hairline) both helped but didn't eliminate it.
- **Operator's overall read**: "better than the local models in some ways, worse in others. There's still some shimmering where the mask fuzzes in and out. Looks like Paul Rudd wearing a Fletcher mask in places." Decided not to push to v4 (512 res, ~$13 more).

### Bugs we paid for in time

The DFL toolchain wasn't designed for Python 3.11 + CUDA 12.4 + numpy 1.26. Each of these cost 5–30 min to find and patch:

1. **`requirements-cuda.txt` is from 2020** — pinned `numpy==1.19.3`, `opencv-python==4.1.0.25`, `tensorflow-gpu==2.4.0`. None of those wheels exist for Python 3.11. Replaced with: `numpy>=1.24,<2.0`, `opencv-python>=4.8`, `tensorflow[and-cuda]==2.15.*`, `tf2onnx>=1.16`. Watch for: TF 2.16+ flips Keras 3 by default, breaks DFL — stay on 2.15.
2. **Deprecated numpy aliases** — DFL source uses `np.int`, `np.float`, etc. Removed in numpy 1.20+. Sed-replace all of `np.{int,float,bool,long,object,str,complex}` with the builtins across `*.py` (excluding venv).
3. **opencv int casting regression** — DFL passes `(w // 2, w // 2)` to `cv2.getRotationMatrix2D()`. With numpy 1.26, that's `(np.int64, np.int64)` and opencv 4.11 rejects it. Wrap with `int(...)`. Spot in `core/imagelib/warp.py:146`.
4. **Python 3.11 multiprocessing-spawn fails** — DFL's `main.py` does `multiprocessing.set_start_method("spawn")` for "Linux fix." On 3.11 in a containerized env, spawn fails with `FileNotFoundError` rebuilding `SemLock` in child processes. Change to `fork`.
5. **`ulimit -n 1024` default** — DFL with fork mode opens too many file descriptors during data loading. Bump to `65536` before launching training.
6. **Insightface install nukes numpy** — `pip install insightface onnxruntime-gpu` upgrades numpy to 2.4, which breaks tensorflow 2.15 (wants <2.0) and ml_dtypes. We didn't actually need insightface for filtering; the existing fletcher data was already identity-pre-filtered. **Lesson: don't install insightface on the same venv as DFL.**
7. **Interactive prompts in headless mode** — DFL training and merge each ask 20–30 interactive questions on first run. Solved with a `pexpect`-driven Python wrapper that watches for known prompt regexes and sends answers in any order. Saw ~30 prompts; full driver in `train_driver.py` / `merge_driver.py` patterns we can reuse.
8. **`--force-gpu-idxs N` parsing bug in merge** — works on `extract`, crashes on `merge` with `TypeError: 'in <string>' requires string as left operand, not int`. Don't use the flag for merge; let pexpect answer the GPU prompt with empty-line default.
9. **Pipeline scripts that pipe through `tail -N`** silently break stdin — DFL's GPU-selection prompt EOF's and hangs forever. Use `tee` or no filter; `tail` buffers AND closes stdin.
10. **`tmux send-keys` doesn't reach a pexpect child** — pexpect parent owns stdin, doesn't forward tmux input to its child. To stop DFL waiting at "Press Enter," kill the tmux session entirely; the model auto-saves at target_iter so nothing is lost.
11. **DFL hangs at "Press Enter to stop training"** when `target_iter` is reached — not a crash, just waiting for input. Either send the Enter via the same stdin pipeline, or kill the session (model already saved). Wrote an autostop watchdog (`autostop_at_100k.sh`) that polls the train log and kills tmux when iter ≥ target.
12. **FLAC-in-MP4 audio refuses to mux** with default ffmpeg. The Microsoft Paul Rudd video has FLAC audio inside an MP4 container. Re-encode to AAC: `-c:a aac -b:a 192k`. (Or `-strict experimental` to keep FLAC, but compatibility worse.)

### Things that worked

- **Pexpect-driven config phase** (one Python script for ~30 prompts). Reusable.
- **Re-extraction at face_type=head, 512 px**. ~5 min on A6000. Drop-rate ~10% for src, ~15% for dst (head is stricter on partial profiles than whole_face).
- **`tmux new-session -d`** for long jobs — survived all our SSH disconnects.
- **The two-stage scp** (data uploaded in parallel with training installation) saved ~10 min wallclock.

### Cost discipline notes

- **Idle pod = $0.49/hr**. Even a 30-min "I'll be back" is $0.25.
- **Stopped pod ≠ free**: 100 GB Volume disk costs $0.20/GB/mo when stopped = ~$20/mo or $0.67/day. Use **Network Volume** ($0.07/GB/mo) instead next time so storage is cheaper AND survives pod termination.
- **Training is GPU-bound, but face-extract is not**. We did extract on the same A6000 we used for training — would've been cheaper to do extract on a smaller GPU pod, but the orchestration overhead wasn't worth saving ~$0.30.

### Per-target quality verdict for the DFL run

| Target | Round | Recipe | Outcome |
|---|---|---|---|
| Paul Rudd Microsoft commercial (60s) | v1 | DFL SAEHD-LIAE-UDT 256 / wf, 100k iter, default merge | Recognizable Fletcher swap, but Rudd's forehead shows through, face area visibly softer than surrounding 1080p video |
| Same target | v3 | DFL SAEHD-LIAE-UDT 384 / **head**, 100k iter, merge with mask erode -40 / blur 70 / super-res 100 / color rct | Forehead now in swap region; face still softer than 1080p surround; some frame-to-frame mask shimmer remains. Operator: "better than v1 in some ways, worse in others." Did not push to v4 (512 res). |

### Trained-model artifacts

The fletcher_head SAEHD checkpoint is archived at `~/Desktop/fletcher_dfl_archive/` (~1.7 GB across 8 files). If you want to resume:
- Spin up an A6000 RunPod with Network Volume this time.
- Restore the iperov/nagadit fork (with all 12 patches above applied — see `/workspace/DeepFaceLab/` history) to `/workspace/DeepFaceLab/`.
- Drop the archive files into `/workspace/DeepFaceLab/workspace/model/` to skip retraining.
- Continue training (toward 200k+) or merge against a new target.

### Forward-looking — Higgsfield

A separate Sable operator is trying **Higgsfield** for face/identity work (2026-04-27). It's a hosted commercial product with its own training and inference pipeline, no DFL toolchain headaches. Worth comparing outputs on the same Paul Rudd target before committing more time to DFL on local rented GPUs.

If Higgsfield produces a meaningfully better result on the same target with comparable cost, **the DFL-on-RunPod path is no longer the right default for hero clips** and we'd revise the recommendation in this file. Until that comparison exists, treat both as plausible options for "needs more identity than FaceFusion can deliver."

---

## Open questions / next experiments

- [x] FaceFusion `hyperswap_1c_256` + pixel boost vs roop `inswapper_128` — confirmed FaceFusion strictly stronger; `hififace_unofficial_256` strongest on hard targets.
- [x] Codeformer at low blend — preserves identity; recipe in `Sharpening recipe` above.
- [x] Full DeepFaceLab fine-tune on rented GPU — tried, see post-mortem above. **Decent quality, real-cost ~$13, real-time ~22 hours including debug. Not a clear win over FaceFusion for the cost.**
- [ ] **Higgsfield trial** (in progress with another operator) — compare result on Paul Rudd Microsoft target against the v3 DFL output at `~/Desktop/fletcher_as_rudd_v3.mp4`. If Higgsfield wins on quality + cost + time, demote DFL-on-RunPod to "only when Higgsfield can't do it."
- [ ] Cloud-only options worth a paid trial run for hero clips: Replicate `lucataco/faceswap`, Sieve hosted FaceFusion (claims pixel_boost 1024), DeepSwapAI/Akool commercial models.
- [ ] Add a perceptual-diff guard inside `sable/face/swapper.py` — refuse to count a Replicate run as successful (and log cost) if the output is effectively a re-encode of the target.
- [ ] Decide whether `sable face local` is its own subcommand or a `--backend=local` flag on the existing `sable face` command.
- [ ] When the local CLI is wired up, expose `--reference-frame N` and warn loudly if the target clip contains multiple faces without it (see #7).
