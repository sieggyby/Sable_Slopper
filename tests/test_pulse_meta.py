"""Acceptance tests for sable pulse meta — behavioral tests per spec."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from statistics import median

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tweet(tweet_id="t1", author_handle="@alice", likes=100, replies=10,
               reposts=20, quotes=5, bookmarks=5, video_views=0,
               format_bucket="standalone_text", posted_at="2026-03-20T12:00:00+00:00",
               is_quote_tweet=False, is_thread=False, thread_length=1,
               has_image=False, has_video=False, has_link=False,
               video_duration=None, text="test tweet", author_followers=10000):
    return {
        "tweet_id": tweet_id,
        "author_handle": author_handle,
        "likes": likes,
        "replies": replies,
        "reposts": reposts,
        "quotes": quotes,
        "bookmarks": bookmarks,
        "video_views": video_views,
        "format_bucket": format_bucket,
        "posted_at": posted_at,
        "is_quote_tweet": is_quote_tweet,
        "is_thread": is_thread,
        "thread_length": thread_length,
        "has_image": has_image,
        "has_video": has_video,
        "has_link": has_link,
        "video_duration": video_duration,
        "text": text,
        "author_followers": author_followers,
        "attributes": [],
    }


def make_author_history(n=20, likes=100, replies=10, reposts=20, quotes=5,
                         format_bucket="standalone_text"):
    """Build uniform author history for predictable median calculations."""
    return [
        make_tweet(
            tweet_id=f"h{i}",
            likes=likes,
            replies=replies,
            reposts=reposts,
            quotes=quotes,
            format_bucket=format_bucket,
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# normalize.py tests
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_basic_lift_calculation(self):
        """Author median total 100 → tweet with 300 total → lift 3.0."""
        from sable.pulse.meta.normalize import compute_author_lift, MAX_LIFT

        # Build history with median total = 100 (likes=70, replies=10, reposts=15, quotes=5 = 100)
        history = make_author_history(n=20, likes=70, replies=10, reposts=15, quotes=5)
        tweet = make_tweet(tweet_id="test1", likes=210, replies=30, reposts=45, quotes=15)

        result = compute_author_lift(tweet, history)
        assert abs(result.total_lift - 3.0) < 0.01

    def test_zero_reply_floor(self):
        """Minimum denominator prevents extreme lifts from near-zero baselines."""
        from sable.pulse.meta.normalize import compute_author_lift, MAX_LIFT

        # Author with near-zero replies (median = 0 or very low)
        history = make_author_history(n=20, likes=100, replies=0, reposts=10, quotes=0)
        tweet = make_tweet(tweet_id="t_zero", likes=100, replies=7, reposts=10, quotes=0)

        result = compute_author_lift(tweet, history)
        # replies_lift should not be 7/0 = infinite. It must be clamped.
        assert result.replies_lift <= MAX_LIFT
        assert result.replies_lift > 0

    def test_clamped_at_max_lift(self):
        """10,000 likes from author with median 50 → clamped at MAX_LIFT (20.0), not 200."""
        from sable.pulse.meta.normalize import compute_author_lift, MAX_LIFT

        history = make_author_history(n=20, likes=50, replies=5, reposts=5, quotes=2)
        tweet = make_tweet(tweet_id="viral", likes=10000, replies=5, reposts=5, quotes=2)

        result = compute_author_lift(tweet, history)
        assert result.likes_lift == MAX_LIFT
        assert result.total_lift <= MAX_LIFT

    def test_thin_history_fallback(self):
        """Author with 3 tweets → grade 'fallback' with weight 0.25."""
        from sable.pulse.meta.normalize import compute_author_lift

        history = make_author_history(n=3)
        tweet = make_tweet(tweet_id="t_thin", likes=100, replies=10, reposts=10, quotes=5)

        result = compute_author_lift(tweet, history)
        assert result.author_quality.grade == "fallback"
        assert result.author_quality.weight == 0.25

    def test_weighted_mean_lower_with_fallback(self):
        """weighted_mean_lift lower when half tweets from fallback authors vs all strong."""
        from sable.pulse.meta.normalize import AuthorNormalizedTweet, AuthorQuality, weighted_mean_lift

        def make_ant(lift: float, grade: str, weight: float) -> AuthorNormalizedTweet:
            aq = AuthorQuality(grade=grade, total_tweets=20, total_scans=1,
                               reasons=[], weight=weight)
            return AuthorNormalizedTweet(
                tweet_id="x", author_handle="@x", format_bucket="standalone_text",
                attributes=[], posted_at="", text="",
                likes=0, replies=0, reposts=0, quotes=0, bookmarks=0, video_views=0,
                author_followers=0, author_median_likes=0, author_median_replies=0,
                author_median_reposts=0, author_median_quotes=0, author_median_total=0,
                likes_lift=lift, replies_lift=lift, reposts_lift=lift, quotes_lift=lift,
                total_lift=lift,
                author_median_same_format=0, format_lift=lift, format_lift_reliable=False,
                author_quality=aq,
            )

        strong_tweets = [make_ant(3.0, "strong", 1.0) for _ in range(5)]
        mixed_tweets = (
            [make_ant(3.0, "strong", 1.0) for _ in range(3)] +
            [make_ant(3.0, "fallback", 0.25) for _ in range(3)]
        )

        assert abs(weighted_mean_lift(strong_tweets) - 3.0) < 0.01
        assert abs(weighted_mean_lift(mixed_tweets) - 3.0) < 0.01

        # Both have lift 3.0 but mixed is still 3.0 (same lift value);
        # the test verifies that weight differences affect aggregation when lifts differ
        # Let's make fallback authors have higher lift to test the downweighting
        mixed2 = (
            [make_ant(3.0, "strong", 1.0) for _ in range(3)] +
            [make_ant(10.0, "fallback", 0.25) for _ in range(3)]
        )
        result_high_fallback = weighted_mean_lift(mixed2)
        # Fallback authors contribute 0.25 weight each vs 1.0 for strong
        # Strong: 3 * 3.0 * 1.0 = 9.0 | Fallback: 3 * 10.0 * 0.25 = 7.5
        # Total weight: 3*1 + 3*0.25 = 3.75
        # Result: 16.5 / 3.75 = 4.4
        expected = (3 * 3.0 * 1.0 + 3 * 10.0 * 0.25) / (3 * 1.0 + 3 * 0.25)
        assert abs(result_high_fallback - expected) < 0.01

    def test_weighted_mean_skips_zero_history_fallback(self):
        """Undefined lifts from zero-history fallback tweets must not poison aggregation."""
        from sable.pulse.meta.normalize import compute_author_lift, weighted_mean_lift

        strong = compute_author_lift(
            make_tweet(tweet_id="strong", author_handle="@strong", likes=210, replies=30, reposts=45, quotes=15),
            make_author_history(n=20, likes=70, replies=10, reposts=15, quotes=5),
        )
        zero_history = compute_author_lift(
            make_tweet(tweet_id="zero", author_handle="@zero", likes=1, replies=0, reposts=0, quotes=0),
            [],
        )

        assert zero_history.total_lift is None
        assert abs(weighted_mean_lift([strong, zero_history]) - strong.total_lift) < 0.01

    def test_no_lift_exceeds_max(self):
        """Invariant: no lift value ever exceeds MAX_LIFT."""
        from sable.pulse.meta.normalize import compute_author_lift, MAX_LIFT

        history = make_author_history(n=20, likes=1, replies=1, reposts=1, quotes=1)
        tweet = make_tweet(tweet_id="mega", likes=99999, replies=9999, reposts=9999, quotes=9999)

        result = compute_author_lift(tweet, history)
        assert result.likes_lift <= MAX_LIFT
        assert result.replies_lift <= MAX_LIFT
        assert result.reposts_lift <= MAX_LIFT
        assert result.quotes_lift <= MAX_LIFT
        assert result.total_lift <= MAX_LIFT
        assert result.format_lift <= MAX_LIFT

    def test_no_denom_below_min_denom(self):
        """Invariant: no denominator less than min_denom in lift calculations."""
        from sable.pulse.meta.normalize import compute_author_lift, MAX_LIFT

        # Very low engagement history
        history = make_author_history(n=20, likes=0, replies=0, reposts=0, quotes=0)
        tweet = make_tweet(tweet_id="zero_hist", likes=5, replies=3, reposts=2, quotes=1)

        result = compute_author_lift(tweet, history)
        # With all-zero history, medians would be 0. min_denom = max(2, 5% of median_total)
        # median_total = 0, so min_denom = 2
        # All denominators should be floored at min_denom (2)
        # Result: lifts should be finite and clamped
        assert result.total_lift >= 0
        assert result.total_lift <= MAX_LIFT


# ---------------------------------------------------------------------------
# fingerprint.py tests
# ---------------------------------------------------------------------------

class TestFingerprint:
    def test_short_clip_classification(self):
        """Video 25s, not QT → short_clip."""
        from sable.pulse.meta.fingerprint import classify_format
        bucket = classify_format(has_video=True, video_duration=25, is_quote_tweet=False)
        assert bucket == "short_clip"

    def test_qt_overrides_video(self):
        """QT + video → quote_tweet (QT has highest priority)."""
        from sable.pulse.meta.fingerprint import classify_format
        bucket = classify_format(is_quote_tweet=True, has_video=True, video_duration=25)
        assert bucket == "quote_tweet"

    def test_thread_overrides_image(self):
        """Thread + image → thread (thread takes priority over image)."""
        from sable.pulse.meta.fingerprint import classify_format
        bucket = classify_format(is_thread=True, thread_length=4, has_image=True)
        assert bucket == "thread"

    def test_long_clip(self):
        """Video 90s, not QT → long_clip."""
        from sable.pulse.meta.fingerprint import classify_format
        bucket = classify_format(has_video=True, video_duration=90, is_quote_tweet=False)
        assert bucket == "long_clip"

    def test_single_image(self):
        """Image, no video, not QT → single_image."""
        from sable.pulse.meta.fingerprint import classify_format
        bucket = classify_format(has_image=True, has_video=False, is_quote_tweet=False)
        assert bucket == "single_image"

    def test_standalone_text(self):
        """No media, no link, not thread/QT → standalone_text."""
        from sable.pulse.meta.fingerprint import classify_format
        bucket = classify_format()  # all defaults
        assert bucket == "standalone_text"

    def test_classify_format_never_returns_none(self):
        """classify_format() always returns a non-empty string from FORMAT_BUCKETS."""
        from sable.pulse.meta.fingerprint import classify_format, FORMAT_BUCKETS
        # Test all combinations
        combos = [
            {},
            {"is_quote_tweet": True},
            {"is_thread": True, "thread_length": 3},
            {"has_video": True, "video_duration": 30},
            {"has_video": True, "video_duration": 120},
            {"has_image": True},
            {"has_link": True},
            {"has_image": True, "has_video": True},
            {"is_quote_tweet": True, "has_video": True},
        ]
        for combo in combos:
            result = classify_format(**combo)
            assert result is not None
            assert result != ""
            assert result in FORMAT_BUCKETS, f"Got {result!r} for {combo}"

    def test_all_returns_in_format_buckets(self):
        """Invariant: all classify_format returns are in FORMAT_BUCKETS."""
        from sable.pulse.meta.fingerprint import classify_format, FORMAT_BUCKETS
        for is_qt in [True, False]:
            for is_thread in [True, False]:
                for has_video in [True, False]:
                    for has_image in [True, False]:
                        for has_link in [True, False]:
                            result = classify_format(
                                is_quote_tweet=is_qt,
                                is_thread=is_thread,
                                thread_length=3 if is_thread else 1,
                                has_video=has_video,
                                video_duration=30 if has_video else None,
                                has_image=has_image,
                                has_link=has_link,
                            )
                            assert result in FORMAT_BUCKETS

    def test_no_trend_code_uses_archetype_names(self):
        """Invariant: trend/baselines/quality modules don't import from recommender."""
        import ast
        import importlib.util

        files_to_check = ["trends", "baselines", "quality"]
        archetype_names = set()
        from sable.pulse.meta.recommender import RECOMMENDATION_ARCHETYPES
        archetype_names = set(RECOMMENDATION_ARCHETYPES.keys())

        base = Path(__file__).parent.parent / "sable" / "pulse" / "meta"
        for fname in files_to_check:
            fpath = base / f"{fname}.py"
            source = fpath.read_text()
            for name in archetype_names:
                # Check that archetype names don't appear as string literals in trend code
                assert f'"{name}"' not in source, (
                    f"Archetype name '{name}' found in {fname}.py — violates invariant"
                )
                assert f"'{name}'" not in source, (
                    f"Archetype name '{name}' found in {fname}.py — violates invariant"
                )


# ---------------------------------------------------------------------------
# topics.py tests
# ---------------------------------------------------------------------------

class TestTopics:
    def test_ticker_extraction(self):
        """$TIG extracted from tweet text."""
        from sable.pulse.meta.topics import extract_terms
        terms = extract_terms("$TIG is going to change everything")
        assert "$TIG" in terms

    def test_denylist_filters_real(self):
        """'The Real Yield' should NOT be extracted (denylist filters 'The')."""
        from sable.pulse.meta.topics import extract_terms
        terms = extract_terms("the real yield from staking is insane")
        # The cap-phrase regex requires capital letters; lowercase doesn't match
        assert "The Real Yield" not in terms
        assert "Real Yield" not in terms  # "Real" starts caps but "Yield" also starts caps
        # Actually "Real Yield" could match. But "The" is in denylist, not "Real"
        # The denylist filters on the FIRST word of the cap phrase.
        # "Real" is not in DENY_TERMS so "Real Yield" might extract — but text is lowercase
        # so no cap phrases anyway
        # Verify no terms contain "Real" in this lowercase text
        for t in terms:
            assert "The Real" not in t

    def test_denylist_filters_capitalized(self):
        """'The Real Yield' as capitalized → denylist removes it."""
        from sable.pulse.meta.topics import extract_terms
        terms = extract_terms("The Real Yield from staking is insane")
        assert "The Real Yield" not in terms  # "The" is in DENY_TERMS

    def test_repeated_ngrams_extraction(self):
        """'real yield' extracted if 5 tweets from 3 different authors contain it."""
        from sable.pulse.meta.topics import extract_repeated_ngrams
        tweets = [
            {"text": "the real yield from staking", "author_handle": "@alice"},
            {"text": "real yield is what matters", "author_handle": "@bob"},
            {"text": "real yield real yield", "author_handle": "@charlie"},
            {"text": "real yield discussion today", "author_handle": "@alice"},
            {"text": "why real yield beats apr", "author_handle": "@dave"},
        ]
        ngrams = extract_repeated_ngrams(tweets, min_occurrences=3, min_unique_authors=2)
        assert "real yield" in ngrams

    def test_synonym_merging(self):
        """TEE and 'trusted execution environment' merge into canonical TEE."""
        from sable.pulse.meta.topics import merge_terms
        synonyms = {"TEE": ["trusted execution environment", "secure enclave"]}
        terms = {
            "TEE": {"count": 3, "authors": {"@a", "@b"}, "lift_sum": 6.0},
            "trusted execution environment": {"count": 2, "authors": {"@c"}, "lift_sum": 4.0},
        }
        merged = merge_terms(terms, synonyms)
        assert "TEE" in merged
        assert merged["TEE"]["count"] == 5
        assert len(merged["TEE"]["authors"]) == 3

    def test_no_empty_strings_in_terms(self):
        """Invariant: extract_terms never returns empty strings."""
        from sable.pulse.meta.topics import extract_terms
        texts = [
            "",
            "   ",
            "hello world",
            "#crypto #defi",
            "$BTC $ETH",
            "normal tweet with nothing special",
        ]
        for text in texts:
            terms = extract_terms(text)
            for t in terms:
                assert t != "", f"Empty string in terms for text: {text!r}"
                assert len(t) > 1, f"Single char term {t!r} for text: {text!r}"


# ---------------------------------------------------------------------------
# quality.py tests
# ---------------------------------------------------------------------------

class TestQuality:
    def _make_normalized(self, n: int, unique_authors: int, lift: float = 2.0,
                          grade: str = "strong") -> list:
        from sable.pulse.meta.normalize import AuthorNormalizedTweet, AuthorQuality
        weight = {"strong": 1.0, "adequate": 0.8, "weak": 0.5, "fallback": 0.25}[grade]
        aq = AuthorQuality(grade=grade, total_tweets=20, total_scans=1, reasons=[], weight=weight)
        authors = [f"@author{i % unique_authors}" for i in range(n)]
        return [
            AuthorNormalizedTweet(
                tweet_id=f"t{i}", author_handle=authors[i],
                format_bucket="standalone_text", attributes=[],
                posted_at="2026-03-20T12:00:00+00:00", text="test",
                likes=100, replies=10, reposts=20, quotes=5,
                bookmarks=5, video_views=0, author_followers=10000,
                author_median_likes=100, author_median_replies=10,
                author_median_reposts=20, author_median_quotes=5,
                author_median_total=135,
                likes_lift=lift, replies_lift=lift, reposts_lift=lift,
                quotes_lift=lift, total_lift=lift,
                author_median_same_format=135, format_lift=lift,
                format_lift_reliable=True, author_quality=aq,
            )
            for i in range(n)
        ]

    def _make_normalized_tweet(self, tweet_id: str, author_handle: str, lift: float | None,
                               grade: str = "strong"):
        from sable.pulse.meta.normalize import AuthorNormalizedTweet, AuthorQuality

        weight = {"strong": 1.0, "adequate": 0.8, "weak": 0.5, "fallback": 0.25}[grade]
        aq = AuthorQuality(grade=grade, total_tweets=20, total_scans=1, reasons=[], weight=weight)
        return AuthorNormalizedTweet(
            tweet_id=tweet_id,
            author_handle=author_handle,
            format_bucket="standalone_text",
            attributes=[],
            posted_at="2026-03-20T12:00:00+00:00",
            text="test",
            likes=100,
            replies=10,
            reposts=20,
            quotes=5,
            bookmarks=5,
            video_views=0,
            author_followers=10000,
            author_median_likes=100,
            author_median_replies=10,
            author_median_reposts=20,
            author_median_quotes=5,
            author_median_total=135,
            likes_lift=lift,
            replies_lift=lift,
            reposts_lift=lift,
            quotes_lift=lift,
            total_lift=lift,
            author_median_same_format=135,
            format_lift=lift,
            format_lift_reliable=True,
            author_quality=aq,
        )

    def test_high_quality_a_grade(self):
        """20 tweets, 12 unique authors, not concentrated → grade A."""
        from sable.pulse.meta.quality import assess_format_quality
        tweets = self._make_normalized(20, 12, lift=2.0)
        quality = assess_format_quality(tweets)
        assert quality.confidence == "A"

    def test_few_tweets_c_grade(self):
        """3 tweets, 2 unique authors → grade C (insufficient sample)."""
        from sable.pulse.meta.quality import assess_format_quality
        tweets = self._make_normalized(3, 2)
        quality = assess_format_quality(tweets)
        assert quality.confidence == "C"

    def test_concentration_flag(self):
        """15 tweets, top 2 authors contributing 60% → concentrated flag, grade downgrade."""
        from sable.pulse.meta.normalize import AuthorNormalizedTweet, AuthorQuality
        from sable.pulse.meta.quality import assess_format_quality

        aq_strong = AuthorQuality(grade="strong", total_tweets=20, total_scans=1,
                                   reasons=[], weight=1.0)

        tweets = []
        # 2 dominant authors with high lift
        for i in range(9):
            tweets.append(AuthorNormalizedTweet(
                tweet_id=f"dominant_{i}", author_handle="@dominant",
                format_bucket="standalone_text", attributes=[],
                posted_at="2026-03-20T12:00:00+00:00", text="",
                likes=0, replies=0, reposts=0, quotes=0, bookmarks=0, video_views=0,
                author_followers=100000, author_median_likes=100, author_median_replies=10,
                author_median_reposts=20, author_median_quotes=5, author_median_total=135,
                likes_lift=5.0, replies_lift=5.0, reposts_lift=5.0, quotes_lift=5.0,
                total_lift=5.0, author_median_same_format=135, format_lift=5.0,
                format_lift_reliable=True, author_quality=aq_strong,
            ))
        # Many authors with low lift — so top 2 dominate the total_lift sum
        for i in range(6):
            tweets.append(AuthorNormalizedTweet(
                tweet_id=f"minor_{i}", author_handle=f"@minor_{i}",
                format_bucket="standalone_text", attributes=[],
                posted_at="2026-03-20T12:00:00+00:00", text="",
                likes=0, replies=0, reposts=0, quotes=0, bookmarks=0, video_views=0,
                author_followers=1000, author_median_likes=10, author_median_replies=1,
                author_median_reposts=2, author_median_quotes=0, author_median_total=13,
                likes_lift=1.0, replies_lift=1.0, reposts_lift=1.0, quotes_lift=1.0,
                total_lift=1.0, author_median_same_format=13, format_lift=1.0,
                format_lift_reliable=True, author_quality=aq_strong,
            ))

        quality = assess_format_quality(tweets)
        assert quality.concentration > 0.50
        # Concentration should be flagged in reasons
        assert any("concentrated" in r for r in quality.confidence_reasons)

    def test_all_fallback_capped_at_b(self):
        """All fallback authors → max confidence B even with good sample/diversity."""
        from sable.pulse.meta.quality import assess_format_quality
        tweets = self._make_normalized(20, 12, lift=3.0, grade="fallback")
        quality = assess_format_quality(tweets)
        assert quality.confidence in ("B", "C")
        assert quality.confidence != "A"
        assert quality.all_fallback is True

    def test_outlier_skew_variance(self):
        """4 tweets: 3 near 1.0x, 1 at MAX_LIFT → weighted_mean ~5.75x, variance noted."""
        from sable.pulse.meta.normalize import AuthorNormalizedTweet, AuthorQuality
        from sable.pulse.meta.quality import assess_format_quality, aggregate_lifts

        aq = AuthorQuality(grade="strong", total_tweets=20, total_scans=1, reasons=[], weight=1.0)

        def make_t(tweet_id, lift):
            return AuthorNormalizedTweet(
                tweet_id=tweet_id, author_handle=f"@a{tweet_id}",
                format_bucket="standalone_text", attributes=[],
                posted_at="2026-03-20T12:00:00+00:00", text="",
                likes=0, replies=0, reposts=0, quotes=0, bookmarks=0, video_views=0,
                author_followers=10000, author_median_likes=100, author_median_replies=10,
                author_median_reposts=20, author_median_quotes=5, author_median_total=135,
                likes_lift=lift, replies_lift=lift, reposts_lift=lift, quotes_lift=lift,
                total_lift=lift, author_median_same_format=135, format_lift=lift,
                format_lift_reliable=True, author_quality=aq,
            )

        tweets = [make_t("a", 1.0), make_t("b", 1.0), make_t("c", 1.0), make_t("d", 20.0)]
        agg = aggregate_lifts(tweets, method="weighted_mean")
        # (1+1+1+20)/4 = 5.75 (all equal weight since all strong)
        assert abs(agg - 5.75) < 0.01

        quality = assess_format_quality(tweets)
        # High variance in small bucket should be noted
        has_variance_note = any("variance" in r or "range" in r for r in quality.confidence_reasons)
        assert has_variance_note

    def test_mixed_quality_contradiction(self):
        """Fallback authors at 8x + strong authors at 1.2x → aggregate near 1.2x, warning surfaced."""
        from sable.pulse.meta.normalize import AuthorNormalizedTweet, AuthorQuality
        from sable.pulse.meta.quality import assess_format_quality, aggregate_lifts

        def make_t(tweet_id, author, lift, grade, weight):
            aq = AuthorQuality(grade=grade, total_tweets=20, total_scans=1, reasons=[], weight=weight)
            return AuthorNormalizedTweet(
                tweet_id=tweet_id, author_handle=author,
                format_bucket="standalone_text", attributes=[],
                posted_at="2026-03-20T12:00:00+00:00", text="",
                likes=0, replies=0, reposts=0, quotes=0, bookmarks=0, video_views=0,
                author_followers=10000, author_median_likes=100, author_median_replies=10,
                author_median_reposts=20, author_median_quotes=5, author_median_total=135,
                likes_lift=lift, replies_lift=lift, reposts_lift=lift, quotes_lift=lift,
                total_lift=lift, author_median_same_format=135, format_lift=lift,
                format_lift_reliable=True, author_quality=aq,
            )

        # 8 fallback authors at 8x, 4 strong authors at 1.2x
        tweets = (
            [make_t(f"fb{i}", f"@fb{i}", 8.0, "fallback", 0.25) for i in range(8)] +
            [make_t(f"st{i}", f"@st{i}", 1.2, "strong", 1.0) for i in range(4)]
        )

        agg = aggregate_lifts(tweets, method="weighted_mean")
        # Weights: 8 * 0.25 + 4 * 1.0 = 2.0 + 4.0 = 6.0
        # Weighted sum: 8 * 8.0 * 0.25 + 4 * 1.2 * 1.0 = 16.0 + 4.8 = 20.8
        # Result: 20.8 / 6.0 ≈ 3.47
        expected = (8 * 8.0 * 0.25 + 4 * 1.2 * 1.0) / (8 * 0.25 + 4 * 1.0)
        assert abs(agg - expected) < 0.01
        # Result is pulled strongly toward strong authors (1.2x) due to weights
        # The aggregate (3.47) is much less than fallback avg (8.0)

        quality = assess_format_quality(tweets)
        # Should surface mixed quality warning
        assert quality.mixed_quality_warning != ""

    def test_quality_assessment_skips_zero_history_fallback_lifts(self):
        """Zero-history fallback tweets with undefined lift should not crash or suppress real warnings."""
        from sable.pulse.meta.normalize import compute_author_lift
        from sable.pulse.meta.quality import assess_format_quality

        zero_history = compute_author_lift(
            make_tweet(tweet_id="zero", author_handle="@zero", likes=1, replies=0, reposts=0, quotes=0),
            [],
        )
        tweets = [
            zero_history,
            self._make_normalized_tweet("fb", "@fb", 8.0, grade="fallback"),
            self._make_normalized_tweet("st1", "@st1", 1.0, grade="strong"),
            self._make_normalized_tweet("st2", "@st2", 1.0, grade="strong"),
        ]

        quality = assess_format_quality(tweets)

        assert zero_history.total_lift is None
        assert quality.sample_count == 4
        assert quality.unique_authors == 4
        assert quality.mixed_quality_warning != ""

    def test_confidence_always_abc(self):
        """Invariant: confidence is always A, B, or C."""
        from sable.pulse.meta.quality import assess_format_quality
        for n in [0, 1, 3, 8, 20]:
            tweets = self._make_normalized(n, max(n, 1))
            quality = assess_format_quality(tweets)
            assert quality.confidence in ("A", "B", "C")

    def test_confidence_reasons_never_empty(self):
        """Invariant: every EngagementQuality has non-empty confidence_reasons."""
        from sable.pulse.meta.quality import assess_format_quality
        for n in [0, 3, 10, 20]:
            tweets = self._make_normalized(n, max(n, 1))
            quality = assess_format_quality(tweets)
            assert len(quality.confidence_reasons) > 0

    def test_aggregate_method_selection(self):
        """Config key aggregation_method selects between methods."""
        from sable.pulse.meta.quality import aggregate_lifts
        tweets = []  # empty — returns 0.0 regardless
        result = aggregate_lifts(tweets, method="weighted_mean")
        assert result == 0.0

        with pytest.raises(NotImplementedError):
            aggregate_lifts([self._make_normalized(4, 4)[0]], method="weighted_median")

        with pytest.raises(NotImplementedError):
            aggregate_lifts([self._make_normalized(4, 4)[0]], method="winsorized_mean")


# ---------------------------------------------------------------------------
# analyzer.py tests
# ---------------------------------------------------------------------------

class TestAnalyzer:
    def test_run_analysis_passes_org_context_to_shared_wrapper(self, monkeypatch):
        """Org-scoped pulse/meta analysis must use the shared wrapper with org_id."""
        from sable.pulse.meta.analyzer import run_analysis
        from sable.pulse.meta.quality import EngagementQuality
        from sable.pulse.meta.trends import TrendResult

        wrapper_calls = []

        def fake_call_claude_json(prompt, **kwargs):
            wrapper_calls.append({"prompt": prompt, **kwargs})
            return json.dumps({
                "dominant_format": "standalone_text",
                "dominant_format_why": "Text posts are outperforming baseline.",
                "execution_notes": "Lead with a sharp hook.",
                "topic_categorization": {"hot": [], "rising": [], "emerging": []},
                "topic_confidence": "low",
                "meta_summary": "Post a standalone text update now.",
            })

        monkeypatch.setattr("sable.shared.api.call_claude_json", fake_call_claude_json)

        quality = EngagementQuality(
            confidence="B",
            confidence_reasons=["adequate sample"],
            sample_count=4,
            unique_authors=4,
            concentration=0.25,
            all_fallback=False,
            mixed_quality_warning="",
        )
        trends = {
            "standalone_text": TrendResult(
                format_bucket="standalone_text",
                current_lift=2.0,
                lift_vs_30d=1.8,
                lift_vs_7d=1.2,
                trend_status="rising",
                momentum="accelerating",
                confidence="B",
                confidence_reasons=["adequate sample"],
                quality=quality,
                reasons=["Current lift above baseline."],
                gate_failures=[],
            )
        }

        parsed, raw = run_analysis([], trends, [], org="testorg", model="claude-sonnet-4-6")

        assert parsed["dominant_format"] == "standalone_text"
        assert raw
        assert len(wrapper_calls) == 1
        assert wrapper_calls[0]["org_id"] == "testorg"
        assert wrapper_calls[0]["call_type"] == "pulse_meta_analysis"


# ---------------------------------------------------------------------------
# trends.py tests
# ---------------------------------------------------------------------------

class TestTrends:
    def _make_normalized(self, n: int, lift: float, unique_authors: int = None) -> list:
        from sable.pulse.meta.normalize import AuthorNormalizedTweet, AuthorQuality
        if unique_authors is None:
            unique_authors = n
        aq = AuthorQuality(grade="strong", total_tweets=20, total_scans=1, reasons=[], weight=1.0)
        return [
            AuthorNormalizedTweet(
                tweet_id=f"t{i}", author_handle=f"@a{i % unique_authors}",
                format_bucket="standalone_text", attributes=[],
                posted_at="2026-03-20T12:00:00+00:00", text="",
                likes=100, replies=10, reposts=20, quotes=5,
                bookmarks=5, video_views=0, author_followers=10000,
                author_median_likes=50, author_median_replies=5,
                author_median_reposts=10, author_median_quotes=2, author_median_total=67,
                likes_lift=lift, replies_lift=lift, reposts_lift=lift, quotes_lift=lift,
                total_lift=lift,
                author_median_same_format=67, format_lift=lift,
                format_lift_reliable=True, author_quality=aq,
            )
            for i in range(n)
        ]

    def test_surging_label(self):
        """Current lift 3.0x vs 30d baseline 1.0x → surging."""
        from sable.pulse.meta.trends import analyze_format_trend
        tweets = self._make_normalized(10, 3.0, unique_authors=5)
        result = analyze_format_trend(
            format_bucket="standalone_text",
            tweets=tweets,
            baseline_30d=1.0,
            baseline_7d=1.0,
            baseline_days_available=10,
        )
        assert result.trend_status == "surging"
        assert result.lift_vs_30d == pytest.approx(3.0, rel=0.05)

    def test_decelerating_momentum(self):
        """lift_vs_30d = 3.0x but lift_vs_7d = 0.7x → decelerating."""
        from sable.pulse.meta.trends import analyze_format_trend, classify_momentum
        momentum = classify_momentum(lift_vs_30d=3.0, lift_vs_7d=0.7)
        assert momentum == "decelerating"

    def test_insufficient_baseline_no_label(self):
        """Only 3 days of baseline → no trend label."""
        from sable.pulse.meta.trends import analyze_format_trend
        tweets = self._make_normalized(10, 3.0, unique_authors=5)
        result = analyze_format_trend(
            format_bucket="standalone_text",
            tweets=tweets,
            baseline_30d=1.0,
            baseline_7d=1.0,
            baseline_days_available=3,  # below min_baseline_days=5
        )
        assert result.trend_status is None
        assert any("baseline" in f.lower() for f in result.gate_failures)

    def test_no_label_when_gates_fail(self):
        """Invariant: no trend label when quality gates not met."""
        from sable.pulse.meta.trends import analyze_format_trend
        # Too few tweets
        tweets = self._make_normalized(2, 3.0, unique_authors=2)
        result = analyze_format_trend(
            format_bucket="standalone_text",
            tweets=tweets,
            baseline_30d=1.0,
            baseline_7d=1.0,
            baseline_days_available=10,
        )
        assert result.trend_status is None
        assert len(result.gate_failures) > 0


# ---------------------------------------------------------------------------
# recommender.py tests
# ---------------------------------------------------------------------------

class TestRecommender:
    def _make_trend(self, status: str, confidence: str, lift: float = 2.0) -> object:
        from sable.pulse.meta.trends import TrendResult
        from sable.pulse.meta.quality import EngagementQuality
        quality = EngagementQuality(
            confidence=confidence,
            confidence_reasons=["test"],
            sample_count=10,
            unique_authors=5,
            concentration=0.3,
            all_fallback=False,
            mixed_quality_warning="",
        )
        return TrendResult(
            format_bucket="standalone_text",
            current_lift=lift,
            lift_vs_30d=lift,
            lift_vs_7d=lift,
            trend_status=status,
            momentum="plateauing",
            confidence=confidence,
            confidence_reasons=[f"confidence {confidence}"],
            quality=quality,
            reasons=[f"{status} format"],
            gate_failures=[],
        )

    def test_fatigue_penalty_reduces_priority(self):
        """Content posted 3x same org has lower priority than unposted content."""
        from sable.pulse.meta.recommender import compute_priority
        trend = self._make_trend("surging", "A", lift=2.5)

        fresh_content = {"type": "text_tweet", "posted_by": [], "org": "tig", "topics": []}
        used_content = {
            "type": "text_tweet",
            "org": "tig",
            "topics": [],
            "posted_by": [
                {"account": "@x", "org": "tig"},
                {"account": "@y", "org": "tig"},
                {"account": "@z", "org": "tig"},
            ],
        }

        fresh_score, _ = compute_priority(trend, fresh_content, "@alice", None)
        used_score, _ = compute_priority(trend, used_content, "@alice", None)
        assert fresh_score > used_score

    def test_recommendations_sorted_descending(self):
        """Post Now sorted by priority descending."""
        from sable.pulse.meta.recommender import build_recommendations

        class FakeAccount:
            handle = "@testaccount"
            org = "tig"
            learned_preferences: dict = {}

        trends = {
            "standalone_text": self._make_trend("surging", "A", lift=2.5),
            "short_clip": self._make_trend("rising", "B", lift=1.8),
        }

        result = build_recommendations(
            trends=trends,
            accounts=[FakeAccount()],
            vault_path=None,
            analysis={},
        )
        post_now = result["post_now"]
        if len(post_now) > 1:
            for i in range(len(post_now) - 1):
                assert post_now[i].priority_score >= post_now[i + 1].priority_score

    def test_non_zero_priority(self):
        """Invariant: every Post Now recommendation has non-zero priority."""
        from sable.pulse.meta.recommender import compute_priority
        trend = self._make_trend("surging", "A", lift=2.5)
        content = {"type": "text_tweet", "posted_by": [], "org": "tig", "topics": []}
        score, _ = compute_priority(trend, content, "@alice", None)
        assert score > 0

    def test_recommendation_required_fields(self):
        """Invariant: every recommendation has all required fields."""
        from sable.pulse.meta.recommender import build_recommendations, PostNowRecommendation

        class FakeAccount:
            handle = "@testaccount"
            org = "tig"
            learned_preferences: dict = {}

        trends = {"standalone_text": self._make_trend("surging", "A", lift=2.5)}

        # With vault path None, no content found → all formats become gaps
        result = build_recommendations(
            trends=trends,
            accounts=[FakeAccount()],
            vault_path=None,
            analysis={},
        )

        # Check gap has required fields
        gaps = result["gaps_to_fill"]
        if gaps:
            gap = gaps[0]
            assert "format" in gap
            assert "content_type" in gap  # INVARIANT: always specifies content type

    def test_reason_shows_numeric_drivers(self):
        """Reason field surfaces numeric priority drivers."""
        from sable.pulse.meta.recommender import compute_priority
        trend = self._make_trend("surging", "A", lift=2.5)
        content = {"type": "text_tweet", "posted_by": [], "org": "tig", "topics": []}
        score, reason = compute_priority(trend, content, "@alice", None, days_idle=3)
        # Reason should contain numeric values
        assert "Priority" in reason
        # Should contain at least one number
        import re
        numbers = re.findall(r'\d+', reason)
        assert len(numbers) >= 2

    def test_stop_doing_no_vault_refs(self):
        """Invariant: Pane 2 (Stop Doing) never references vault content."""
        from sable.pulse.meta.recommender import build_recommendations

        trends = {"standalone_text": self._make_trend("dead", "A", lift=0.3)}

        result = build_recommendations(
            trends=trends,
            accounts=[],
            vault_path=None,
            analysis={},
        )
        stops = result["stop_doing"]
        for s in stops:
            # Should have format and evidence, not content IDs or file paths
            assert "format" in s
            assert "evidence" in s
            assert "file_path" not in s
            assert "content_id" not in s

    def test_gaps_specify_content_type(self):
        """Invariant: Pane 3 (Gaps) always specifies what content type to produce."""
        from sable.pulse.meta.recommender import build_recommendations

        trends = {"short_clip": self._make_trend("surging", "A", lift=3.0)}

        result = build_recommendations(
            trends=trends,
            accounts=[],
            vault_path=None,
            analysis={},
        )
        gaps = result["gaps_to_fill"]
        if gaps:
            for gap in gaps:
                assert "content_type" in gap
                assert gap["content_type"]  # non-empty


# ---------------------------------------------------------------------------
# reporter.py invariants (unit-level checks)
# ---------------------------------------------------------------------------

class TestReporter:
    def _make_trend(self, status, confidence, lift=2.0, concentration=0.3,
                    unique_authors=8, sample_count=15) -> object:
        from sable.pulse.meta.trends import TrendResult
        from sable.pulse.meta.quality import EngagementQuality
        quality = EngagementQuality(
            confidence=confidence,
            confidence_reasons=["test"],
            sample_count=sample_count,
            unique_authors=unique_authors,
            concentration=concentration,
            all_fallback=False,
            mixed_quality_warning="",
        )
        return TrendResult(
            format_bucket="standalone_text",
            current_lift=lift,
            lift_vs_30d=lift,
            lift_vs_7d=lift,
            trend_status=status,
            momentum="plateauing",
            confidence=confidence,
            confidence_reasons=[f"confidence {confidence}"],
            quality=quality,
            reasons=[],
            gate_failures=[],
        )

    def test_bootstrapping_header_shown(self):
        """Invariant: bootstrapping header appears when below min_baseline_days."""
        from io import StringIO
        from rich.console import Console
        from sable.pulse.meta.reporter import render_report

        buf = StringIO()
        c = Console(file=buf, width=120)
        # Patch the module-level console
        import sable.pulse.meta.reporter as reporter_mod
        orig_console = reporter_mod.console
        reporter_mod.console = c

        try:
            render_report(
                org="tig",
                trends={"standalone_text": self._make_trend("surging", "A")},
                topic_signals=[],
                recommendations={"post_now": [], "stop_doing": [], "gaps_to_fill": []},
                analysis={},
                baseline_days=2,  # below min_baseline_days=5
                min_baseline_days=5,
            )
        finally:
            reporter_mod.console = orig_console

        output = buf.getvalue()
        assert "Building baseline" in output or "building" in output.lower()

    def test_confidence_and_authors_in_trend_output(self):
        """Invariant: every trend line shows confidence grade + unique author count."""
        from io import StringIO
        from rich.console import Console
        from sable.pulse.meta.reporter import _render_format_trends
        import sable.pulse.meta.reporter as reporter_mod

        buf = StringIO()
        c = Console(file=buf, width=200)
        orig_console = reporter_mod.console
        reporter_mod.console = c

        try:
            _render_format_trends(
                {"standalone_text": self._make_trend("surging", "A", unique_authors=8)},
                baseline_days=10,
                min_baseline_days=5,
            )
        finally:
            reporter_mod.console = orig_console

        output = buf.getvalue()
        # Confidence grade A should appear
        assert "A" in output
        # Author count 8 should appear
        assert "8" in output


# ---------------------------------------------------------------------------
# T3: insert_post returns True for new, False for duplicate
# ---------------------------------------------------------------------------

def test_insert_post_returns_true_for_new_false_for_duplicate(tmp_path, monkeypatch):
    """insert_post returns True on first insert, False on duplicate."""
    monkeypatch.setenv("SABLE_HOME", str(tmp_path))
    import importlib
    import sable.shared.paths as _paths
    import sable.pulse.db as _db
    importlib.reload(_paths)
    importlib.reload(_db)

    _db.migrate()
    conn = _db.get_conn()
    first = _db.insert_post(
        post_id="p1",
        account_handle="@test",
        text="hello",
        url="http://example.com",
        posted_at="2024-01-01T00:00:00",
    )
    second = _db.insert_post(
        post_id="p1",
        account_handle="@test",
        text="hello",
        url="http://example.com",
        posted_at="2024-01-01T00:00:00",
    )
    assert first is True, "First insert should return True"
    assert second is False, "Duplicate insert should return False"
    rows = conn.execute("SELECT COUNT(*) FROM posts WHERE id='p1'").fetchone()[0]
    assert rows == 1, "Only one row should exist after duplicate insert"
    conn.close()


# ---------------------------------------------------------------------------
# T4: zero-history through aggregation does not crash
# ---------------------------------------------------------------------------

def test_zero_history_fallback_does_not_crash_aggregation():
    """Zero-history tweet with None lifts should not crash weighted_mean_lift or assess_format_quality."""
    from sable.pulse.meta.normalize import AuthorNormalizedTweet, AuthorQuality, weighted_mean_lift, compute_author_lift
    from sable.pulse.meta.quality import assess_format_quality

    # Use compute_author_lift with empty history to get a real zero-history result
    zero_history = compute_author_lift(
        make_tweet(tweet_id="zero", author_handle="@zero", likes=5, replies=0, reposts=0, quotes=0),
        [],
    )

    assert zero_history.total_lift is None

    # weighted_mean_lift should not crash and should return 0.0 (no valid lifts)
    result = weighted_mean_lift([zero_history])
    assert result == 0.0, f"Expected 0.0 from zero-history tweet, got {result}"

    # assess_format_quality should not crash
    quality = assess_format_quality([zero_history])
    assert quality is not None
    assert quality.confidence in ("A", "B", "C")
