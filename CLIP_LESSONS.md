# Clip Quality Lessons

Tracked failures, fixes, and open problems from iterating the clip pipeline.

---

## What's Working

- **Window detection** — pause-bounded window segmentation reliably finds speech blocks. The 0.8s threshold cuts at natural silences without over-splitting.
- **Variant generation** — short/medium/long variants from `_candidate_endpoints` are the right abstraction. Having 3 real endpoints per clip is better than a single snap.
- **Batch eval structure** — one Claude call for all clips (Option B) is efficient and gives Claude cross-clip context for relative scoring.
- **Dry-run pipeline** — `--dry-run` flag works end-to-end, skips Claude calls, and returns sane metadata.
- **Transcript extraction** — `yt-dlp` + `whisper` pipeline handles YouTube URLs directly; word-level timestamps are reliable.

---

## What's Not Working

### Clips cluster at the long variant (43–47s range)
- Root cause: `_candidate_endpoints` had a 0.3s pause threshold. Many real sentence boundaries have shorter pauses (0.15–0.29s), so few candidates were found and short/medium collapsed toward long.
- Fix: lowered threshold to 0.15s with a 0.05s fallback tier if fewer than 3 candidates found.

### No kill mechanism
- A clip that is pure intro setup (no landing moment) was allowed through because `_evaluate_variants_batch` could only choose short/medium/long — no discard option.
- Fix: added `kill` flag to the batch eval response. Claude can now kill a clip with a reason.

### Brainrot loops visibly (>2x)
- Root cause: `pick()` selected randomly from energy-matched candidates without regard for clip duration. A 15s brainrot source was looped 3x for a 46.7s clip.
- Fix: `pick()` now prefers sources where `source_duration >= clip_duration / 2` (max 2x loop), falling back to any match if nothing long enough exists.

### Clips end mid-argument
- Root cause: `_evaluate_variants_batch` had no way to signal that the long variant still cut off before the point resolved.
- Fix: added `extend` flag. When `extend=true`, the pipeline searches up to 20s beyond the long variant endpoint for the next clean pause-backed sentence boundary.

---

## What's Been Tried

- **Option A** (individual Claude calls per clip): too slow, no cross-clip context.
- **Option B** (single Claude call for all clips with short/medium/long variants): current approach, works well for throughput but needs kill/extend to handle edge cases.
- **0.3s pause threshold in `_candidate_endpoints`**: too high — real sentence endpoints have 0.15–0.25s pauses in fast-paced crypto interviews.

---

## What Needs More Work (Next Iteration)

- **Leading filler trim** — ✓ Done (2026-03-26). `_trim_leading_filler` advances clip start past "so", "um", "yeah", bigrams like "you know" / "i mean". Max 4s window; negligible moves (<0.1s) no-op'd. Removed "and"/"now"/"right" from list — too common as crypto interview pivots.
- **Context backtrack for dangling references** — ✓ Done (2026-03-26). `_backtrack_for_context` detects danglers ("that's why", "which means", "because of this", etc.) and backtracks start to prior sentence-ending segment. Aborts on window-boundary crossing (≥0.8s pause), duration contract violation, or >12s backtrack.
- **Per-clip score logging in CLI output** — ✓ Done (2026-03-26). Score column added to dry-run table; score shown in assembly status line.
- **Brainrot theme matching** — e.g. space/tech topics paired with thematically fitting brainrot. Currently only energy-matched.

---

## Lessons by Clip (TIG/Fletcher interview — W11 2026)

| Clip | Issue | Root Cause |
|------|-------|------------|
| 3 | Cut before point landed | Long variant still mid-argument; no extend mechanism |
| 4 | Pure intro setup, no landing | No kill flag; batch eval forced to pick a variant |
| 6 | Intro-only, no finishing moment | Same as clip 4 |
| 7 | Brainrot looped 3x (15s source, 46.7s clip) | `pick()` duration-blind |
| 3,4,6,7 | All in 43–47s range | Pause threshold too high → few candidates → collapsed to long |
