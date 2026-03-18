"""Markdown profile file system for per-account rich context."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from sable.shared.paths import profile_dir

PROFILE_FILES = ["tone", "interests", "context", "notes"]

_TEMPLATES = {
    "tone": """\
# Tone — {handle}

**Voice style**: [e.g. dry wit, hype, analytical, shitposter]

**Language patterns**: [phrases they use, slang, formatting habits]

**What to avoid**: [topics, language, vibes that don't fit this account]

**Example phrases**:
-
-
""",
    "interests": """\
# Interests — {handle}

**Primary topics**: [DeFi, L2s, memecoins, NFTs, etc.]

**Crypto sub-communities**: [which corners of CT they inhabit]

**Non-crypto interests**: [gaming, sports, culture — anything that bleeds into content]

**Current meta**: [what's hot in their niche right now]
""",
    "context": """\
# Context — {handle}

**Background**: [who is this person/account, how did they build their following]

**Community standing**: [rep, relationships, known for what]

**Brand moments**: [notable posts, controversies, memes they originated]

**Account lore**: [inside jokes, recurring bits, community memory]
""",
    "notes": """\
# Ops Notes — {handle}

**What's landed**: [content formats, topics, vibes that performed well]

**What flopped**: [things to avoid repeating]

**Current arcs**: [ongoing narratives or series to continue]

**Open loops**: [things to follow up on]
""",
}


def scaffold_profile(handle: str) -> Path:
    """Create blank profile files for an account. Returns the profile directory."""
    handle = handle if handle.startswith("@") else f"@{handle}"
    d = profile_dir(handle)
    d.mkdir(parents=True, exist_ok=True)
    for name in PROFILE_FILES:
        fpath = d / f"{name}.md"
        if not fpath.exists():
            fpath.write_text(_TEMPLATES[name].format(handle=handle))
    return d


def read_profile_file(handle: str, file: str) -> Optional[str]:
    """Read a single profile file. Returns None if it doesn't exist."""
    handle = handle if handle.startswith("@") else f"@{handle}"
    fpath = profile_dir(handle) / f"{file}.md"
    if fpath.exists():
        return fpath.read_text()
    return None


def write_profile_file(handle: str, file: str, content: str) -> None:
    """Write/overwrite a profile file."""
    handle = handle if handle.startswith("@") else f"@{handle}"
    d = profile_dir(handle)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{file}.md").write_text(content)


def load_profiles(handle: str, files: Optional[list[str]] = None) -> dict[str, str]:
    """Load profile files into a dict {filename: content}. Missing files are omitted."""
    files = files or PROFILE_FILES
    result = {}
    for name in files:
        content = read_profile_file(handle, name)
        if content is not None:
            result[name] = content
    return result


def profiles_exist(handle: str) -> bool:
    handle = handle if handle.startswith("@") else f"@{handle}"
    d = profile_dir(handle)
    return d.exists() and any((d / f"{f}.md").exists() for f in PROFILE_FILES)


def format_profiles_for_prompt(profiles: dict[str, str]) -> str:
    """Format loaded profiles into a prompt-injectable string."""
    if not profiles:
        return ""
    sections = []
    for name, content in profiles.items():
        sections.append(f"=== {name.upper()} PROFILE ===\n{content.strip()}")
    return "\n\n".join(sections)


def profile_preview(handle: str, lines: int = 5) -> dict[str, str]:
    """Return first N lines of each profile file for display."""
    profiles = load_profiles(handle)
    return {
        name: "\n".join(content.splitlines()[:lines])
        for name, content in profiles.items()
    }
