"""Tests for character_explainer/script.py — truncate_to_last_sentence()."""
from __future__ import annotations

import pytest

from sable.character_explainer.script import truncate_to_last_sentence


# ─────────────────────────────────────────────────────────────────────
# truncate_to_last_sentence
# ─────────────────────────────────────────────────────────────────────

def test_truncate_short_text_unchanged():
    text = "Hello world."
    result = truncate_to_last_sentence(text, max_words=100)
    assert result == text


def test_truncate_empty_string():
    assert truncate_to_last_sentence("", max_words=10) == ""


@pytest.mark.parametrize("punctuation", [".", "!", "?"])
def test_truncate_finds_last_sentence_boundary(punctuation):
    # 5 words before boundary, then more words after to force truncation
    prefix = f"Short sentence{punctuation}"
    filler = " extra words " * 20
    text = prefix + filler
    result = truncate_to_last_sentence(text, max_words=8)
    # Result must end with the boundary punctuation
    assert result.endswith(punctuation)
    # Result must not be longer than max_words (plus punctuation)
    assert len(result.split()) <= 8


def test_truncate_no_boundary_returns_truncated_words():
    # No sentence-ending punctuation — falls back to first max_words words
    text = "one two three four five six seven eight nine ten"
    result = truncate_to_last_sentence(text, max_words=5)
    assert result == "one two three four five"


def test_truncate_result_ends_at_sentence_not_mid_word():
    text = "This is sentence one. This is sentence two. This is a very long third sentence that goes on."
    # max_words=10 puts the cut inside sentence three; should truncate back to "sentence two."
    result = truncate_to_last_sentence(text, max_words=10)
    assert result.endswith(".")
    # Must contain complete sentences only
    assert "sentence two" in result
