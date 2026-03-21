"""Claude API clip selection — window-based two-stage selector."""
from __future__ import annotations

import json

from sable.roster.models import Account
from sable.shared.api import build_account_context, call_claude_json


_PAUSE_THRESHOLD = 0.8      # seconds of silence between words → window boundary
_MIN_WINDOW_DURATION = 5.0  # discard windows shorter than this


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
    Resolve a Claude selection (window indices) to precise timestamps.
    - start = windows[min_idx].start
    - end = windows[max_idx].end, snapped to nearest sentence+pause boundary
    - Skip if resolved duration < min_dur
    - Trim to max_dur hard cap if over
    """
    indices = selection.get("windows", [])
    if not indices:
        return None

    lo = min(indices)
    hi = max(indices)
    if lo >= len(windows) or hi >= len(windows):
        return None

    start = windows[lo]["start"]
    end = windows[hi]["end"]

    # Try to snap end to a sentence boundary followed by a pause >= 0.3s
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
            # Try sentence snap within a small window
            end = _snap_to_sentence_end(trim_target, segments, tolerance=5.0)
            if end - start > max_dur + 2.0:
                end = trim_target  # hard cut

    return {
        "start": start,
        "end": end,
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

    # Build condensed window list for Claude
    window_lines = []
    for i, w in enumerate(windows):
        dur = w["end"] - w["start"]
        text = w["text"].replace("\n", " ")
        if dur > 60.0 and len(text) > 300:
            # Show start + mid + end for very long windows
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

**Merging windows:**
If a complete thought spans two or three consecutive windows, list all their indices.
Example: "windows": [3, 4] merges window 3 and 4 into one clip.

**Scoring:**
Rate each clip 1–10. Only include clips you'd score 6 or higher.

Match the account's voice and topics above. Prioritize moments native to crypto Twitter.

Return a JSON array only. Each element:
{{
  "windows": [<index>, ...],
  "reason": "<why this clip works for this account>",
  "hook": "<the first line/hook for the caption>",
  "caption_hint": "<suggested tweet text>",
  "score": <1-10>
}}

Sort by score descending. Return [] if nothing qualifies."""

    max_tokens = min(max(2048, len(windows) * 80), 8192)
    raw = call_claude_json(prompt, max_tokens=max_tokens)

    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        selections = json.loads(raw)
        if isinstance(selections, dict) and "clips" in selections:
            selections = selections["clips"]
        if not isinstance(selections, list):
            selections = []
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude returned invalid JSON: {e}\nRaw: {raw[:500]}")

    # Sort by score descending
    selections.sort(key=lambda s: s.get("score", 0), reverse=True)

    # Resolve each selection to precise timestamps
    clips = []
    for sel in selections:
        clip = _resolve_clip(sel, windows, words, segments, min_dur=min_duration, max_dur=max_duration)
        if clip is not None:
            clips.append(clip)

    # Apply max_clips cap if provided
    if max_clips is not None:
        clips = clips[:max_clips]

    return clips
