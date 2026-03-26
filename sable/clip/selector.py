"""Claude API clip selection — window-based two-stage selector."""
from __future__ import annotations

import json
import logging

from sable.roster.models import Account
from sable.shared.api import build_account_context, call_claude_json
from sable.shared.retry import retry_with_backoff

_logger = logging.getLogger(__name__)

_PAUSE_THRESHOLD = 0.8      # seconds of silence between words → window boundary
_MIN_WINDOW_DURATION = 5.0  # discard windows shorter than this
_MAX_EVAL_BATCH = 20        # maximum clips per single Claude eval call
_MAX_WINDOW_CONTEXT: int = 80   # why: caps first-stage prompt; keeps input tokens bounded

_FILLER_SINGLE = frozenset({
    "so", "yeah", "yep", "like", "um", "uh",
    "okay", "ok", "well", "alright",
})
_FILLER_BIGRAMS = frozenset({"you know", "i mean"})

_DANGLING_PATTERNS = (
    # Demonstrative + resolution (unambiguous danglers)
    "that's why", "that's what", "that's how", "that is why", "that is what",
    "this is why", "this is what", "this is how",
    # Relative clause openers
    "which means", "which is why", "which is what",
    # Causal continuers
    "because of that", "because of this", "because of it",
    "because that's", "because it's", "because they",
    # Temporal/logical result
    "so that's why", "so that's what", "so that's how",
)


def _candidate_endpoints(
    start: float,
    words: list[dict],
    segments: list[dict],
    min_dur: float = 8.0,
    max_dur: float = 90.0,
) -> list[float]:
    """
    Collect all sentence+pause boundaries between start+min_dur and start+max_dur.
    A qualifying boundary: segment ends with .?! and pause after >= 0.3s (if words available).
    Returns list sorted ascending.
    """
    lo = start + min_dur
    hi = start + max_dur

    def pause_after(t: float) -> float:
        before = [w for w in words if w["end"] <= t + 0.05]
        after = [w for w in words if w["start"] > t + 0.05]
        if not before or not after:
            return 0.0
        return after[0]["start"] - before[-1]["end"]

    candidates = []
    for s in segments:
        if not s["text"].strip().endswith((".", "?", "!")):
            continue
        t = s["end"]
        if t < lo or t > hi:
            continue
        if words and pause_after(t) < 0.15:
            continue
        candidates.append(t)

    # Fallback: if fewer than 3 candidates, lower bar to any detectable pause (0.05s)
    # This ensures short/medium/long have real variance rather than collapsing to one endpoint.
    if len(candidates) < 3:
        all_sentence_ends = [
            s["end"] for s in segments
            if s["text"].strip().endswith((".", "?", "!"))
            and lo <= s["end"] <= hi
        ]
        extras = [
            t for t in all_sentence_ends
            if t not in candidates and (not words or pause_after(t) >= 0.05)
        ]
        candidates = sorted(set(candidates) | set(extras))

    return sorted(set(candidates))


def _clip_text(start: float, end: float, segments: list[dict]) -> str:
    """Extract transcript text for segments whose center falls within [start, end]."""
    overlap = [
        s for s in segments
        if (s["start"] + s["end"]) / 2 >= start and (s["start"] + s["end"]) / 2 <= end
    ]
    return " ".join(s["text"].strip() for s in overlap).strip()


def _snap_to_sentence_end(end: float, segments: list[dict], tolerance: float = 8.0) -> float:
    """Adjust end time to nearest sentence-ending segment within tolerance."""
    sentence_ends = [
        s for s in segments
        if s["text"].strip().endswith((".", "?", "!"))
        and abs(s["end"] - end) <= tolerance
    ]
    if not sentence_ends:
        nearby = [s for s in segments if abs(s["end"] - end) <= tolerance]
        if not nearby:
            return end
        return min(nearby, key=lambda s: abs(s["end"] - end))["end"]
    before = [s for s in sentence_ends if s["end"] <= end]
    if before:
        return max(before, key=lambda s: s["end"])["end"]
    return min(sentence_ends, key=lambda s: abs(s["end"] - end))["end"]


def _find_windows(words: list[dict], segments: list[dict]) -> list[dict]:
    """
    Walk word timestamps and split on pauses >= _PAUSE_THRESHOLD.
    Each window = contiguous speech block. Windows < _MIN_WINDOW_DURATION discarded.
    Text is reconstructed from phrase segments that overlap the window's time range.
    Fallback: if no word timestamps, treat each segment as its own window.
    """
    if not words:
        # Fallback: each segment is a window
        windows = []
        for seg in segments:
            dur = seg["end"] - seg["start"]
            if dur >= _MIN_WINDOW_DURATION:
                windows.append({
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": seg["text"].strip(),
                })
        return windows

    # Group words into windows by pause detection
    raw_windows: list[tuple[float, float]] = []
    win_start = words[0]["start"]
    prev_end = words[0]["end"]

    for w in words[1:]:
        gap = w["start"] - prev_end
        if gap >= _PAUSE_THRESHOLD:
            raw_windows.append((win_start, prev_end))
            win_start = w["start"]
        prev_end = w["end"]
    raw_windows.append((win_start, prev_end))

    # Reconstruct text for each window from phrase segments
    windows = []
    for ws, we in raw_windows:
        dur = we - ws
        if dur < _MIN_WINDOW_DURATION:
            continue
        # Collect segments whose center falls within this window
        overlap = [
            s for s in segments
            if (s["start"] + s["end"]) / 2 >= ws and (s["start"] + s["end"]) / 2 < we
        ]
        text = " ".join(s["text"].strip() for s in overlap).strip()
        if not text:
            # Fall back to word text
            text = " ".join(
                w.get("text", "").strip()
                for w in words
                if w["start"] >= ws and w["end"] <= we + 0.1
            ).strip()
        windows.append({"start": ws, "end": we, "text": text})

    return windows


def _resolve_clip(
    selection: dict,
    windows: list[dict],
    words: list[dict],
    segments: list[dict],
    min_dur: float = 8.0,
    max_dur: float = 90.0,
) -> dict | None:
    """
    Resolve a Claude selection (window indices) to short/medium/long variant timestamps.
    - start = windows[min_idx].start
    - Candidates = sentence+pause boundaries between start+min_dur and start+max_dur
    - short = first candidate, medium = middle, long = last
    - Falls back to current single-snap behavior if no candidates found
    Returns dict with 'variants' key, or None if unresolvable.
    """
    indices = selection.get("windows", [])
    if not indices:
        return None

    lo = min(indices)
    hi = max(indices)
    if lo >= len(windows) or hi >= len(windows):
        return None

    start = windows[lo]["start"]

    # Collect sentence+pause boundaries in the valid duration range
    candidates = _candidate_endpoints(start, words, segments, min_dur=min_dur, max_dur=max_dur)

    if candidates:
        n = len(candidates)
        short_end = candidates[0]
        medium_end = candidates[n // 2]
        long_end = candidates[-1]
    else:
        # Fall back to current single-snap behavior
        end = windows[hi]["end"]
        snapped = _snap_to_pause_backed_sentence(end, words, segments, pause_min=0.3)
        if snapped is not None:
            end = snapped
        else:
            end = _snap_to_sentence_end(end, segments, tolerance=8.0)

        dur = end - start
        if dur < min_dur:
            return None

        if dur > max_dur:
            trim_target = start + max_dur
            trimmed = _snap_to_pause_backed_sentence(trim_target, words, segments, pause_min=0.3)
            if trimmed is not None and (trimmed - start) <= max_dur + 2.0:
                end = trimmed
            else:
                end = _snap_to_sentence_end(trim_target, segments, tolerance=5.0)
                if end - start > max_dur + 2.0:
                    end = trim_target

        short_end = medium_end = long_end = end

    return {
        "start": start,
        "variants": {
            "short":  {"start": start, "end": short_end},
            "medium": {"start": start, "end": medium_end},
            "long":   {"start": start, "end": long_end},
        },
        "reason": selection.get("reason", ""),
        "hook": selection.get("hook", ""),
        "caption_hint": selection.get("caption_hint", ""),
        "score": selection.get("score", 5),
    }


def _snap_to_pause_backed_sentence(
    target: float,
    words: list[dict],
    segments: list[dict],
    pause_min: float = 0.3,
    search_radius: float = 10.0,
) -> float | None:
    """
    Find the nearest sentence-ending segment boundary within search_radius of target
    that is also followed by a silence >= pause_min in the word timestamps.
    Returns None if no qualifying boundary found.
    """
    if not words:
        return None

    candidates = [
        s for s in segments
        if s["text"].strip().endswith((".", "?", "!"))
        and abs(s["end"] - target) <= search_radius
    ]
    if not candidates:
        return None

    # Build a quick lookup of pause durations after each second
    def pause_after(t: float) -> float:
        """Return gap between last word ending at/before t and next word starting after t."""
        before = [w for w in words if w["end"] <= t + 0.05]
        after = [w for w in words if w["start"] > t + 0.05]
        if not before or not after:
            return 0.0
        return after[0]["start"] - before[-1]["end"]

    # Prefer candidates at or before target; only accept forward snap within 2s
    before = []
    after = []
    for s in candidates:
        p = pause_after(s["end"])
        if p >= pause_min:
            if s["end"] <= target:
                before.append(s["end"])
            else:
                after.append(s["end"])

    if before:
        return max(before)

    # Accept a forward snap only if within 2s of target
    close_after = [t for t in after if t - target <= 2.0]
    if close_after:
        return min(close_after)

    return None


def _normalize_word(text: str) -> str:
    return text.strip().lower().rstrip(".,!?;:—")


def _trim_leading_filler(
    start: float,
    words: list[dict],
    max_trim: float = 4.0,
) -> float | None:
    """Advance clip start past leading filler tokens. Returns new start or None."""
    if not words:
        return None
    clip_words = sorted(
        [w for w in words if w["start"] >= start - 0.05],
        key=lambda w: w["start"],
    )
    if not clip_words:
        return None

    deadline = start + max_trim
    cursor = 0

    while cursor < len(clip_words):
        w = clip_words[cursor]
        if w["start"] >= deadline:
            return None  # hit wall — treat as all-filler, no change

        # bigram lookahead
        if cursor + 1 < len(clip_words):
            bigram = (
                _normalize_word(w["text"])
                + " "
                + _normalize_word(clip_words[cursor + 1]["text"])
            )
            if bigram in _FILLER_BIGRAMS:
                cursor += 2
                if cursor >= len(clip_words):
                    return None
                continue

        # single filler
        if _normalize_word(w["text"]) in _FILLER_SINGLE:
            cursor += 1
            if cursor >= len(clip_words):
                return None
            continue

        # first non-filler
        new_start = w["start"]
        if new_start <= start + 0.1:
            return None  # negligible move
        return new_start

    return None  # loop exhausted without non-filler


def _backtrack_for_context(
    start: float,
    words: list[dict],
    segments: list[dict],
    max_dur: float,
    end: float,
    max_backtrack: float = 12.0,
) -> float | None:
    """
    If clip start is a dangling reference, backtrack to the start of the prior
    sentence. Returns new start or None. Aborts if backtrack would cross a speech
    window boundary or violate the duration contract.
    """
    # Step 1: extract first ~6 tokens from clip start
    if words:
        clip_words = [w for w in words if w["start"] >= start - 0.05]
        first_tokens = [_normalize_word(w["text"]) for w in clip_words[:6]]
    else:
        clip_segs = [s for s in segments if s["start"] >= start - 0.05]
        if not clip_segs:
            return None
        first_tokens = clip_segs[0]["text"].strip().lower().split()[:6]

    if not first_tokens:
        return None

    prefix = " ".join(first_tokens)

    # Step 2: pattern match (longest-first ordering prevents short-pattern shadowing)
    if not any(prefix.startswith(p) for p in _DANGLING_PATTERNS):
        return None

    # Step 3: find immediately prior sentence-ending segment
    prior_segs = [
        s for s in segments
        if s["end"] < start - 0.05
        and s["text"].strip().endswith((".", "?", "!"))
    ]
    if not prior_segs:
        return None

    boundary_seg = max(prior_segs, key=lambda s: s["end"])
    new_start = boundary_seg["start"]

    # Step 4: hard limit — max backtrack distance
    if start - new_start > max_backtrack:
        return None

    # Step 5: window-boundary check — abort if the range crosses a ≥0.8s pause
    # (backtracking across a window boundary adds silence the windowing excluded)
    if words:
        range_words = [w for w in words if new_start - 0.05 <= w["start"] <= start + 0.05]
        for j in range(len(range_words) - 1):
            gap = range_words[j + 1]["start"] - range_words[j]["end"]
            if gap >= _PAUSE_THRESHOLD:
                return None

    # Step 6: duration contract — abort if the extended clip exceeds max_dur
    if end - new_start > max_dur:
        return None

    return new_start


def _evaluate_variants_batch(
    clips_with_variants: list[dict],
    segments: list[dict],
    words: list[dict] | None = None,
    max_dur: float = 90.0,
) -> list[dict]:
    """
    One Claude call to pick the best duration variant per clip.
    Supports kill (discard unusable clips) and extend (search beyond long endpoint).
    Returns resolved clips with start/end chosen from the winning variant.
    If len(clips_with_variants) > _MAX_EVAL_BATCH, splits into batches of _MAX_EVAL_BATCH.
    """
    if not clips_with_variants:
        return []

    if len(clips_with_variants) > _MAX_EVAL_BATCH:
        _logger.warning(
            "Clip batch size %d exceeds cap %d; batching into groups",
            len(clips_with_variants), _MAX_EVAL_BATCH,
        )
        results = []
        for offset in range(0, len(clips_with_variants), _MAX_EVAL_BATCH):
            batch = clips_with_variants[offset:offset + _MAX_EVAL_BATCH]
            results.extend(_evaluate_variants_batch(batch, segments, words=words, max_dur=max_dur))
        return results

    clip_descriptions = []
    for i, clip in enumerate(clips_with_variants):
        v = clip["variants"]
        parts = [f"Clip {i}: {clip.get('reason', '')}"]
        for label in ("short", "medium", "long"):
            vv = v[label]
            dur = vv["end"] - vv["start"]
            text = _clip_text(vv["start"], vv["end"], segments)
            if len(text) <= 350:
                display = text
            else:
                display = text[:150] + " [...] " + text[-200:]
            parts.append(f'  {label} ({dur:.0f}s): "{display}"')
        clip_descriptions.append("\n".join(parts))

    clips_text = "\n\n".join(clip_descriptions)

    prompt = f"""You are evaluating clip duration variants for crypto Twitter virality.

For each clip below, pick the variant (short/medium/long) that hits hardest.

Criteria:
- The clip makes a complete, self-contained point
- The clip does NOT end while the speaker is mid-thought or mid-sentence
- SHORT IS BETTER. If the short variant ends on a complete sentence that makes a standalone point, pick short — 15-25s clips outperform 45s on TikTok/Reels. Only go medium/long if short genuinely cuts off mid-argument.
- When in doubt between short and medium: pick short.

{clips_text}

Return a JSON array with one object per clip:
[{{
  "clip": 0,
  "chosen": "short"|"medium"|"long",
  "kill": false,
  "kill_reason": null,
  "lands": true,
  "extend": false,
  "reason": "..."
}}]

Kill a clip (kill=true) if:
- It is pure introduction/setup with no concluding point
- It requires context the viewer cannot possibly have
- The speaker is clearly in the middle of an unresolvable back-and-forth with no resolution in any variant
- It is a meandering explanation that builds toward a trivia fact rather than a genuine insight, reframe, or surprise — i.e., the payoff is a number or statistic with no emotional stakes, no "I can't believe that" moment. A viewer would not share this clip unprompted.

Set extend=true if chosen="long" and the argument still hasn't fully resolved (the speaker is still working toward the payoff). We will try to find a later endpoint.

Set lands=false when the chosen variant cuts off before the rhetorical point is complete."""

    raw = retry_with_backoff(lambda: call_claude_json(prompt, max_tokens=1024))  # budget-exempt: clip pipeline has no org context at eval time

    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        evaluations = json.loads(raw)
        if not isinstance(evaluations, list):
            evaluations = []
    except json.JSONDecodeError:
        _logger.warning("Claude eval parse failed, raw=%r", raw[:500])
        # AR5-27: single retry before falling back to []
        try:
            raw2 = call_claude_json(prompt, max_tokens=1024)  # budget-exempt: clip pipeline has no org context at eval time
            raw2 = raw2.strip()
            if raw2.startswith("```"):
                raw2 = raw2.split("\n", 1)[1].rsplit("```", 1)[0]
            evaluations = json.loads(raw2)
            if not isinstance(evaluations, list):
                evaluations = []
        except Exception:
            evaluations = []

    eval_map: dict[int, dict] = {}
    for ev in evaluations:
        idx = ev.get("clip")
        if isinstance(idx, int):
            eval_map[idx] = ev

    resolved = []
    for i, clip in enumerate(clips_with_variants):
        ev = eval_map.get(i, {})
        chosen = ev.get("chosen", "long")
        if chosen not in ("short", "medium", "long"):
            chosen = "long"

        # Kill: discard clips that can't work
        if ev.get("kill"):
            kill_reason = ev.get("kill_reason") or "no reason given"
            print(f"  [kill] clip {i} discarded: {kill_reason}")
            continue

        vv = clip["variants"][chosen]
        end = vv["end"]

        # Extend: chosen is long and still cuts off mid-argument — search further
        should_extend = (ev.get("extend") or not ev.get("lands", True)) and chosen == "long"
        if should_extend and words:
            long_end = clip["variants"]["long"]["end"]
            extend_target = long_end + 5.0
            hard_cap = long_end + 20.0
            if hard_cap <= clip["start"] + max_dur + 20.0:
                extended = _snap_to_pause_backed_sentence(
                    extend_target, words, segments,
                    pause_min=0.2, search_radius=20.0,
                )
                if extended is not None and extended <= hard_cap:
                    print(f"  [extend] clip {i} extended from {long_end:.1f}s to {extended:.1f}s")
                    end = extended

        # --- Post-processing: leading filler trim + context backtrack ---
        clip_start = vv["start"]

        # 1. Filler trim (advance start past opener tokens)
        if words:
            trimmed = _trim_leading_filler(clip_start, words, max_trim=4.0)
            if trimmed is not None:
                _logger.info("  [trim-filler] clip %d start %.1fs → %.1fs", i, clip_start, trimmed)
                clip_start = trimmed

        # 2. Context backtrack (extend start back to prior sentence if dangling ref)
        new_start = _backtrack_for_context(clip_start, words or [], segments, max_dur, end)
        if new_start is not None:
            _logger.info("  [backtrack] clip %d start %.1fs → %.1fs", i, clip_start, new_start)
            clip_start = new_start

        resolved.append({
            "start": clip_start,
            "end": end,
            "reason": clip.get("reason", ""),
            "hook": clip.get("hook", ""),
            "caption_hint": clip.get("caption_hint", ""),
            "score": clip.get("score", 5),
            "variant": chosen,
            "lands": ev.get("lands", True),
        })

    return resolved


def _dedup_selections(selections: list[dict]) -> list[dict]:
    """Remove overlapping selections (shared absolute window index). Input must be
    pre-sorted by score descending. Higher-scored selection wins on overlap."""
    claimed: set[int] = set()
    result = []
    for sel in selections:
        idxs = set(sel.get("windows", []))
        if not idxs or idxs & claimed:
            continue
        claimed |= idxs
        result.append(sel)
    return result


def select_clips(
    transcript: dict,
    account: Account,
    max_clips: int | None = None,
    min_duration: float = 8.0,
    max_duration: float = 90.0,
    dry_run: bool = False,
) -> list[dict]:
    """
    Use Claude to identify the best clip segments from a transcript.
    Uses window-based two-stage selection:
      1. Pre-compute natural speech windows from pause detection
      2. Show Claude condensed window list; Claude picks by index
      3. Resolve indices to precise timestamps using word boundaries

    Returns list of dicts: [{start, end, reason, hook, caption_hint, score}]
    """
    account_context = build_account_context(
        account, profile_files=["tone", "interests", "context"]
    )

    segments = transcript.get("segments", [])
    words = transcript.get("words", [])

    windows = _find_windows(words, segments)

    if dry_run:
        return [{
            "start": 0.0,
            "end": min(30.0, max_duration),
            "reason": f"DRY RUN — first 30s ({len(windows)} windows detected)",
            "hook": "DRY RUN",
            "caption_hint": f"[dry run clip for {account.handle}]",
            "score": 0,
            "window_count": len(windows),
        }]

    if not windows:
        raise RuntimeError("No speech windows found in transcript.")

    # Batched first-stage: process windows in batches of _MAX_WINDOW_CONTEXT
    num_batches = (len(windows) + _MAX_WINDOW_CONTEXT - 1) // _MAX_WINDOW_CONTEXT
    if num_batches > 1:
        _logger.info(
            "Transcript has %d windows; processing in %d batches of up to %d",
            len(windows), num_batches, _MAX_WINDOW_CONTEXT,
        )

    all_raw_selections: list[dict] = []
    for batch_start in range(0, len(windows), _MAX_WINDOW_CONTEXT):
        batch_windows = windows[batch_start : batch_start + _MAX_WINDOW_CONTEXT]

        window_lines = []
        for i, w in enumerate(batch_windows):
            dur = w["end"] - w["start"]
            text = w["text"].replace("\n", " ")
            if dur > 60.0 and len(text) > 300:
                snippet = text[:200] + " … [mid] … " + text[-100:]
            elif len(text) > 300:
                snippet = text[:300] + "…"
            else:
                snippet = text
            window_lines.append(f"[{i}] {w['start']:.1f}s–{w['end']:.1f}s ({dur:.0f}s): \"{snippet}\"")
        windows_text = "\n".join(window_lines)

        prompt = f"""You are a social media content strategist for crypto Twitter.

{account_context}

## Speech Windows (natural pause-bounded blocks):
{windows_text}

## Task
Find ALL genuinely great clips for vertical short-form video (TikTok/Reels/Shorts).
Return 0 clips if nothing is worth clipping — do NOT fill a quota.

CLIP SELECTION PRINCIPLES:

**Hook mechanics (most important):**
Start the clip mid-sentence on something provocative, confusing, or counterintuitive.
NOT: "So we've been working on this for a while..." (buildup, no tension)
YES: "...and that's why Ethereum is fundamentally broken." (in media res, instant question)
The viewer must feel a question in their head within the first 2 seconds or they scroll.

**What makes a good clip:**
- Contrarian claim, bold prediction, or number that surprises
- Moment where speaker says something that reframes what came before
- Self-contained: the clip can be understood without context

**What makes a bad clip:**
- Starts with filler ("So...", "And...", "Yeah, I think...")
- Requires prior context to make sense
- Trails off into a new topic instead of landing a point
- Only partially covers a thought — merges adjacent windows if needed
- Meanders through explanation to arrive at a statistic or factoid — data without stakes is not a clip

**Merging windows:**
If a complete thought spans two or three consecutive windows, list all their indices.
Example: "windows": [3, 4] merges window 3 and 4 into one clip.

**Format:**
Most clips are "standard" (30–60s arguments). Tag a clip "micro" only when the entire point is delivered in a single sentence or two — a one-liner reframe, a punchy counterintuitive claim, a quick zinger. Micro clips should feel complete at 10–20s. Do NOT tag a clip micro if it takes more than two sentences to land the point.
Examples of micro moments: a speaker says one sentence that flips the frame ("the opt-out doesn't work — everyone else keeps going anyway"), then stops or pivots. That's a micro clip. An explanation that builds toward a conclusion is standard, even if the conclusion is sharp.

**Scoring:**
Rate each clip 1–10. Only include clips you'd score 6 or higher.

Match the account's voice and topics above. Prioritize moments native to crypto Twitter.

Return a JSON array only. Each element:
{{
  "windows": [<index>, ...],
  "reason": "<why this clip works for this account>",
  "hook": "<the first line/hook for the caption>",
  "caption_hint": "<suggested tweet text>",
  "score": <1-10>,
  "format": "standard"|"micro"
}}

Sort by score descending. Return [] if nothing qualifies."""

        max_tokens = min(max(2048, len(batch_windows) * 80), 8192)
        raw = call_claude_json(prompt, max_tokens=max_tokens)  # budget-exempt: clip pipeline has no org context at eval time

        try:
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            batch_sels = json.loads(raw)
            if isinstance(batch_sels, dict) and "clips" in batch_sels:
                batch_sels = batch_sels["clips"]
            if not isinstance(batch_sels, list):
                batch_sels = []
        except json.JSONDecodeError as e:
            _logger.warning("Claude batch %d parse failed: %s", batch_start // _MAX_WINDOW_CONTEXT, e)
            batch_sels = []

        # Offset local indices to absolute positions in windows[]
        for sel in batch_sels:
            sel["windows"] = [idx + batch_start for idx in sel.get("windows", [])]

        all_raw_selections.extend(batch_sels)

    # Sort by score descending, then deduplicate overlapping window spans
    all_raw_selections.sort(key=lambda s: s.get("score", 0), reverse=True)
    selections = _dedup_selections(all_raw_selections)

    # Resolve each selection to short/medium/long variant timestamps
    clips_with_variants = []
    for sel in selections:
        is_micro = sel.get("format") == "micro"
        clip = _resolve_clip(
            sel, windows, words, segments,
            min_dur=5.0 if is_micro else min_duration,
            max_dur=22.0 if is_micro else max_duration,
        )
        if clip is not None:
            clips_with_variants.append(clip)

    # One Claude call to pick the best duration variant per clip
    clips = _evaluate_variants_batch(clips_with_variants, segments, words=words, max_dur=max_duration)

    # Apply max_clips cap if provided
    if max_clips is not None:
        clips = clips[:max_clips]

    return clips
