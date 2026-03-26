"""Vault directory creation and seeding."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sable.vault.notes import write_note
from sable.vault.topics import add_topic
from sable.vault.voices import generate_voice_profiles


_SUBDIRS = [
    "strategy",
    "voices",
    "content/clips",
    "content/explainers",
    "content/memes",
    "content/faceswaps",
    "topics",
    "posting-log",
    "pulse",
    "_sable-internal",
]

_VOICE_TEMPLATE = """---
type: voice_template
---

# Voice Profile Template

Copy this file to `voices/@handle.md` and fill in details.

## Fields
- **handle** — Twitter handle (@...)
- **archetype** — e.g. "degen analyst", "CT insider", "ecosystem builder"
- **voice** — One-sentence voice description
- **topics** — List of core topics
- **avoid** — Topics/tones to avoid
"""


def init_vault(org: str, vault_path: Path) -> None:
    """Create vault directory tree and seed initial pages."""
    vault_path.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    for sub in _SUBDIRS:
        (vault_path / sub).mkdir(parents=True, exist_ok=True)

    # Voice template
    template_path = vault_path / "voices" / "_voice-template.md"
    if not template_path.exists():
        template_path.write_text(_VOICE_TEMPLATE, encoding="utf-8")

    # Strategy placeholder
    strategy_readme = vault_path / "strategy" / "README.md"
    if not strategy_readme.exists():
        strategy_readme.write_text(
            f"# Strategy — {org}\n\nAdd strategy docs here.\n",
            encoding="utf-8",
        )

    # Seed topics from org accounts
    _seed_topics(org, vault_path)

    # Seed voice profiles
    generate_voice_profiles(org, vault_path)

    # Write initial index
    from sable.vault.dashboard import regenerate_index
    regenerate_index(org, vault_path)


def _seed_topics(org: str, vault_path: Path) -> None:
    """Create topic hub pages for all topics across org accounts."""
    from sable.roster.manager import list_accounts

    accounts = list_accounts(org=org)
    seen: set[str] = set()

    for acc in accounts:
        for topic in (acc.persona.topics or []):
            slug = _slugify(topic)
            if slug and slug not in seen:
                seen.add(slug)
                topic_path = vault_path / "topics" / f"{slug}.md"
                if not topic_path.exists():
                    add_topic(slug, topic, org, vault_path)


def _slugify(text: str) -> str:
    """Convert topic name to a filesystem-safe slug."""
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = slug.strip("-")
    return slug
