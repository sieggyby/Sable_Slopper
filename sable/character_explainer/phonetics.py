"""Phonetic correction utilities for TTS pre-processing and caption alignment."""
from __future__ import annotations

import re
import difflib


def parse_phonetic_corrections(md_text: str) -> dict[str, str]:
    """Extract word→replacement pairs from a '## Phonetic Corrections' section."""
    corrections: dict[str, str] = {}
    in_section = False
    for line in md_text.splitlines():
        if re.match(r"^##\s+Phonetic Corrections", line):
            in_section = True
            continue
        if in_section:
            if line.startswith("##"):
                break  # next section — stop
            m = re.match(r"^[-*]\s+(.+?)\s+→\s+(.+)$", line)
            if m:
                corrections[m.group(1).strip()] = m.group(2).strip()
    return corrections


def apply_phonetic_corrections(text: str, corrections: dict[str, str]) -> str:
    """Apply whole-word substitutions to text before TTS synthesis."""
    for word, replacement in corrections.items():
        text = re.sub(rf"\b{re.escape(word)}\b", replacement, text)
    return text


def align_to_script(
    whisper_words: list[dict],
    original_text: str,
) -> list[dict]:
    """
    Replace Whisper word text with original script words, keeping Whisper timing.

    Uses SequenceMatcher to align normalized token sequences. For matched pairs,
    script text + Whisper timing. For dropped/inserted tokens, interpolate or drop.
    """
    def normalize(w: str) -> str:
        return re.sub(r"[^\w]", "", w).lower()

    script_tokens = original_text.split()
    whisper_tokens = [w["text"] for w in whisper_words]

    norm_script = [normalize(t) for t in script_tokens]
    norm_whisper = [normalize(t) for t in whisper_tokens]

    matcher = difflib.SequenceMatcher(None, norm_script, norm_whisper, autojunk=False)
    result: list[dict] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal" or tag == "replace":
            # Pair up script tokens with whisper tokens by index
            s_slice = script_tokens[i1:i2]
            w_slice = whisper_words[j1:j2]
            # If lengths differ, use whisper side length (timing source of truth)
            for k in range(min(len(s_slice), len(w_slice))):
                result.append({
                    "start": w_slice[k]["start"],
                    "end": w_slice[k]["end"],
                    "text": s_slice[k],
                })
            # Any extra script tokens without timing: interpolate from last known
            if len(s_slice) > len(w_slice) and w_slice:
                last = result[-1]
                gap = 0.1
                for extra in s_slice[len(w_slice):]:
                    result.append({
                        "start": last["end"],
                        "end": last["end"] + gap,
                        "text": extra,
                    })
                    last = result[-1]
        elif tag == "insert":
            # Whisper hallucinated words not in script — drop them
            pass
        elif tag == "delete":
            # Script words with no Whisper timing — interpolate from last entry
            if result:
                last = result[-1]
                gap = 0.1
                for token in script_tokens[i1:i2]:
                    result.append({
                        "start": last["end"],
                        "end": last["end"] + gap,
                        "text": token,
                    })
                    last = result[-1]

    return result
