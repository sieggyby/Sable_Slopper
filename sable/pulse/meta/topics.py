"""Deterministic topic extraction + ngram analysis + synonym merging."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Denylist: common words that look like terms but aren't
# ---------------------------------------------------------------------------

DENY_TERMS = {
    "The", "This", "That", "What", "Just", "Like", "Good", "New",
    "Big", "Real", "Last", "Next", "More", "Very", "Best", "Most",
    "First", "Also", "Even", "Still", "Much", "Well", "Back",
    "Great", "Long", "High", "Low", "Old", "Full",
}

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of",
    "in", "for", "on", "at", "by", "it", "be", "as", "do",
    "if", "so", "or", "no", "not", "but", "and", "rt", "via",
    "with", "from", "that", "this", "have", "has", "had", "i",
    "we", "you", "he", "she", "they", "my", "our", "your",
    "its", "all", "just", "now", "will", "can", "get", "got",
}


@dataclass
class TopicSignal:
    term: str
    mention_count: int
    unique_authors: int
    avg_lift: float
    prev_scan_mentions: int
    acceleration: float


# ---------------------------------------------------------------------------
# Per-tweet term extraction
# ---------------------------------------------------------------------------

def extract_terms(tweet_text: str, org_tags: list[str] | None = None) -> list[str]:
    """Extract notable terms from a single tweet.

    Layers:
    1. $TICKER mentions
    2. Capitalized phrases (2+ words), filtered by denylist
    3. Hashtags
    4. Known org tags (case-insensitive)
    """
    terms: list[str] = []

    # Layer 1: $TICKER mentions
    tickers = re.findall(r'\$[A-Z]{2,10}', tweet_text)
    terms.extend(tickers)

    # Layer 2: Capitalized phrases (2+ consecutive capitalized words)
    caps = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', tweet_text)
    terms.extend([c for c in caps if c.split()[0] not in DENY_TERMS])

    # Layer 3: Hashtags (content only, no #)
    hashtags = re.findall(r'#(\w+)', tweet_text)
    terms.extend(hashtags)

    # Layer 4: Known org tags (case-insensitive)
    if org_tags:
        text_lower = tweet_text.lower()
        for tag in org_tags:
            if tag and tag.lower() in text_lower:
                terms.append(tag)

    # Filter out empty strings and single characters
    terms = [t for t in terms if t and len(t) > 1]

    return list(dict.fromkeys(terms))  # deduplicate, preserve order


# ---------------------------------------------------------------------------
# Cross-tweet ngram extraction
# ---------------------------------------------------------------------------

def extract_repeated_ngrams(
    all_tweets: list[dict],
    min_occurrences: int = 3,
    min_unique_authors: int = 2,
) -> list[str]:
    """Extract lowercased bigrams/trigrams that appear across multiple authors.

    Catches informal topic language like 'real yield', 'token unlock',
    'zk rollup', 'airdrop farming' that capitalized-phrase extraction misses.
    """
    bigram_authors: dict[str, set] = defaultdict(set)
    bigram_counts: Counter = Counter()

    for tweet in all_tweets:
        text = tweet.get("text", "")
        author = tweet.get("author_handle", "")
        words = re.findall(r'[a-z]+', text.lower())
        words = [w for w in words if w not in _STOPWORDS and len(w) > 2]

        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            bigram_counts[bigram] += 1
            bigram_authors[bigram].add(author)

        for i in range(len(words) - 2):
            trigram = f"{words[i]} {words[i+1]} {words[i+2]}"
            bigram_counts[trigram] += 1
            bigram_authors[trigram].add(author)

    return [
        term for term, count in bigram_counts.most_common(50)
        if count >= min_occurrences
        and len(bigram_authors[term]) >= min_unique_authors
    ]


# ---------------------------------------------------------------------------
# Term merging via synonym map
# ---------------------------------------------------------------------------

def merge_terms(
    terms_with_counts: dict[str, dict],
    synonyms: dict[str, list[str]],
) -> dict[str, dict]:
    """Merge synonym terms into canonical forms.

    terms_with_counts: {term -> {"count": int, "authors": set, "lift_sum": float}}
    synonyms: {canonical -> [alias, alias, ...]}
    """
    merged: dict[str, dict] = defaultdict(lambda: {"count": 0, "authors": set(), "lift_sum": 0.0})

    for term, data in terms_with_counts.items():
        canonical = term
        for canon, aliases in synonyms.items():
            if (term.lower() in [a.lower() for a in aliases] or
                    term.lower() == canon.lower()):
                canonical = canon
                break
        merged[canonical]["count"] += data.get("count", 0)
        merged[canonical]["authors"].update(data.get("authors", set()))
        merged[canonical]["lift_sum"] += data.get("lift_sum", 0.0)

    return dict(merged)


# ---------------------------------------------------------------------------
# Full topic aggregation pipeline
# ---------------------------------------------------------------------------

def aggregate_topic_signals(
    tweets: list[dict],
    org_tags: list[str] | None = None,
    synonyms: dict[str, list[str]] | None = None,
    prev_scan_mentions: dict[str, int] | None = None,
) -> list[TopicSignal]:
    """Run full topic detection pipeline on a set of tweets.

    Returns list of TopicSignal objects sorted by unique_authors * avg_lift desc.
    """
    synonyms = synonyms or {}
    prev_scan_mentions = prev_scan_mentions or {}

    # Per-tweet term extraction
    tweet_terms: dict[str, dict] = defaultdict(lambda: {"count": 0, "authors": set(), "lift_sum": 0.0})

    for tweet in tweets:
        text = tweet.get("text", "")
        author = tweet.get("author_handle", "")
        lift = tweet.get("total_lift") or 0.0
        terms = extract_terms(text, org_tags)
        for term in terms:
            tweet_terms[term]["count"] += 1
            tweet_terms[term]["authors"].add(author)
            tweet_terms[term]["lift_sum"] += lift

    # Cross-tweet ngrams
    ngrams = extract_repeated_ngrams(tweets)
    for ngram in ngrams:
        # Find tweets that contain this ngram and sum their lifts
        for tweet in tweets:
            if ngram in tweet.get("text", "").lower():
                author = tweet.get("author_handle", "")
                lift = tweet.get("total_lift") or 0.0
                tweet_terms[ngram]["count"] += 1
                tweet_terms[ngram]["authors"].add(author)
                tweet_terms[ngram]["lift_sum"] += lift

    # Filter empty/single-char terms
    tweet_terms = {
        k: v for k, v in tweet_terms.items()
        if k and len(k) > 1
    }

    # Merge synonyms
    merged = merge_terms(dict(tweet_terms), synonyms)

    # Build TopicSignal objects
    signals: list[TopicSignal] = []
    for term, data in merged.items():
        if not term:
            continue
        count = data["count"]
        authors = data["authors"]
        lift_sum = data["lift_sum"]
        unique_authors = len(authors)
        avg_lift = lift_sum / count if count else 0.0
        prev_mentions = prev_scan_mentions.get(term, 0)
        acceleration = count / prev_mentions if prev_mentions else 0.0

        signals.append(TopicSignal(
            term=term,
            mention_count=count,
            unique_authors=unique_authors,
            avg_lift=avg_lift,
            prev_scan_mentions=prev_mentions,
            acceleration=acceleration,
        ))

    # Sort by unique_authors * avg_lift (descending)
    signals.sort(key=lambda s: s.unique_authors * s.avg_lift, reverse=True)
    return signals


def load_vault_synonyms(vault_path) -> dict[str, list[str]]:
    """Load synonym mappings from vault topic hub pages (aliases frontmatter field)."""
    from pathlib import Path
    synonyms: dict[str, list[str]] = {}
    vault_path = Path(vault_path)
    topics_dir = vault_path / "topics"
    if not topics_dir.exists():
        return synonyms

    try:
        from sable.vault.notes import read_frontmatter
        for md_file in topics_dir.glob("*.md"):
            try:
                fm = read_frontmatter(md_file)
                canonical = fm.get("title") or md_file.stem
                aliases = fm.get("aliases", [])
                if aliases and canonical:
                    synonyms[canonical] = aliases
            except Exception:
                pass
    except ImportError:
        pass

    return synonyms
