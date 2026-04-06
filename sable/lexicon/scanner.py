"""Lexicon scanner — extract community-specific vocabulary from watchlist tweets.

Reuses extract_terms() and extract_repeated_ngrams() from topics.py.
Applies an exclusivity filter to separate community language from generic crypto.
"""
from __future__ import annotations

import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

# Minimum-data thresholds — exported for reuse by narrative tracker
MIN_AUTHORS = 10
MIN_TWEETS = 50
MIN_TERM_APPEARANCES = 3
MIN_TERM_AUTHORS = 2
MAX_AUTHOR_SHARE = 0.25  # term must appear in ≤25% of authors


def scan_lexicon(
    org: str,
    days: int = 14,
    top_n: int = 20,
    conn: sqlite3.Connection | None = None,
) -> tuple[list[dict], dict]:
    """Scan scanned_tweets for community-exclusive vocabulary.

    Returns (terms, meta) where:
        terms: list of dicts sorted by LSR descending
        meta: {"corpus_tweets": int, "corpus_authors": int, "below_threshold": bool}
    """
    if conn is None:
        from sable.pulse.meta.db import get_conn
        conn = get_conn()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    rows = conn.execute(
        """SELECT author_handle, text FROM scanned_tweets
           WHERE org = ? AND posted_at >= ?""",
        (org, cutoff),
    ).fetchall()

    if not rows:
        return [], {"corpus_tweets": 0, "corpus_authors": 0, "below_threshold": True}

    # Count unique authors and tweets
    all_authors = set()
    tweet_dicts: list[dict] = []
    for r in rows:
        all_authors.add(r["author_handle"])
        tweet_dicts.append({"text": r["text"] or "", "author_handle": r["author_handle"]})

    total_authors = len(all_authors)
    total_tweets = len(tweet_dicts)

    if total_authors < MIN_AUTHORS or total_tweets < MIN_TWEETS:
        return [], {"corpus_tweets": total_tweets, "corpus_authors": total_authors, "below_threshold": True}

    # Extract terms from each tweet
    from sable.pulse.meta.topics import extract_terms, extract_repeated_ngrams

    term_counts: Counter = Counter()
    term_authors: dict[str, set[str]] = defaultdict(set)

    for td in tweet_dicts:
        author = td["author_handle"]
        terms = extract_terms(td["text"])
        for t in terms:
            t_lower = t.lower()
            term_counts[t_lower] += 1
            term_authors[t_lower].add(author)

    # Also collect repeated ngrams
    ngrams = extract_repeated_ngrams(tweet_dicts, min_occurrences=MIN_TERM_APPEARANCES,
                                     min_unique_authors=MIN_TERM_AUTHORS)
    for ng in ngrams:
        if ng not in term_counts:
            # Count ngram occurrences from tweet texts
            count = 0
            authors_set: set[str] = set()
            for td in tweet_dicts:
                if ng in td["text"].lower():
                    count += 1
                    authors_set.add(td["author_handle"])
            term_counts[ng] = count
            term_authors[ng] = authors_set

    # Apply exclusivity filter
    results: list[dict] = []
    max_author_count = int(total_authors * MAX_AUTHOR_SHARE)

    for term, count in term_counts.items():
        authors = term_authors[term]
        n_authors = len(authors)

        if count < MIN_TERM_APPEARANCES:
            continue
        if n_authors < MIN_TERM_AUTHORS:
            continue
        if n_authors > max_author_count:
            continue

        lsr = compute_lsr(n_authors, total_authors, count)
        results.append({
            "term": term,
            "mention_count": count,
            "unique_authors": n_authors,
            "total_authors": total_authors,
            "lsr": round(lsr, 4),
        })

    results.sort(key=lambda r: r["lsr"], reverse=True)
    return results[:top_n], {"corpus_tweets": total_tweets, "corpus_authors": total_authors, "below_threshold": False}


def compute_lsr(unique_authors: int, total_authors: int, mention_count: int) -> float:
    """Lexical Spread Rate: (unique_authors / total_authors) * log2(1 + mention_count)."""
    if total_authors <= 0:
        return 0.0
    return (unique_authors / total_authors) * math.log2(1 + mention_count)
