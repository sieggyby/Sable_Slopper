"""Script generation via Claude API."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sable.character_explainer.config import CharacterProfile, ExplainerConfig
from sable.shared.api import get_client, call_claude


@dataclass
class ExplainerScript:
    character_id: str
    topic: str
    full_text: str
    word_count: int
    estimated_duration_s: float


_RULES_BLOCK = """\

---

SCRIPT RULES — follow strictly:

FORMAT:
- Flowing spoken monologue only. No bullet points, no lists, no stage directions, no asterisks.
- Do NOT open with "Today I will explain..." or any meta-commentary. Just start talking.
- Target length: {min_words}–{max_words} words. Do not exceed {max_words} words under any circumstances.

VOICE:
- Stay fully in character. Every sentence should sound like it came from this specific person, not a generic explainer.
- Plain casual speech. No jargon unless the character would use it wrong.

STRUCTURE — this is important:
The script should do ONE thing: make the viewer understand the core concept, via this character's specific lens.

The analogy or comparison the character uses must actually map onto how the thing works — it can be dumb, it can be wrong in funny ways, but the mechanic should transfer. A good analogy here means: if someone watched this and only remembered the analogy, they'd still basically get it.

Comedy comes from HOW the character explains it, not from the analogy being unrelated. The tangent or weird personal story should illuminate something true about the topic, even if accidentally.

Do NOT end on a punchline that abandons the explanation. The character should land somewhere that feels like they think they nailed it — even if they kind of did.
"""

_QUIRKS_BLOCK = """\

Verbal tics to weave in naturally (don't force all of them, pick 2–3):
{quirk_lines}
"""

_BACKGROUND_SUMMARY_PROMPT = """\
You are helping prepare a short explainer video script. Below is detailed background research on a topic.

Extract the single clearest explanation of what this thing IS and how it works — in 3–5 plain sentences max. Focus on the mechanism: what people do, what they get, and why it's different. Cut everything else (tokenomics, risks, governance, legal). This summary will be given to a writer as the factual core they must communicate.

Background:
{background}

Respond with only the summary. No preamble."""


def _distill_background(client, background: str, model: str) -> str:
    """Summarise a long research doc down to 3-5 sentences of core mechanism."""
    prompt = _BACKGROUND_SUMMARY_PROMPT.format(background=background)
    # budget-exempt: character explainer has no org context
    return call_claude(prompt, model=model, max_tokens=256).strip()


def generate_script(
    topic: str,
    background: Optional[str],
    character: CharacterProfile,
    config: ExplainerConfig,
) -> ExplainerScript:
    """Generate an in-character explanation script via Claude."""
    client = get_client()  # kept for compatibility; generation uses call_claude below

    rules = _RULES_BLOCK.format(
        min_words=config.min_script_words,
        max_words=config.max_script_words,
    )
    system = character.system_prompt + rules
    if character.speech_quirks:
        quirk_lines = "\n".join(f'- "{q}"' for q in character.speech_quirks)
        system += _QUIRKS_BLOCK.format(quirk_lines=quirk_lines)

    # Distill long background docs to a tight factual brief before sending to the writer
    if background and len(background.split()) > 200:
        background_brief = _distill_background(client, background, config.claude_model)
    else:
        background_brief = background

    user_parts = [f"Topic to explain: {topic}"]
    if background_brief:
        user_parts.append(f"\nCore facts to communicate (must come through in the script):\n{background_brief}")

    user_message = "\n".join(user_parts)

    # budget-exempt: character explainer has no org context
    text = call_claude(user_message, system=system, model=config.claude_model, max_tokens=512).strip()
    words = text.split()

    # Truncation fallback: if over 1.2× word limit, cut to last complete sentence
    if len(words) > config.max_script_words * 1.2:
        text = truncate_to_last_sentence(text, config.max_script_words)
        words = text.split()

    word_count = len(words)
    # Rough estimate: average 2.5 words/second for speech
    estimated_duration_s = word_count / 2.5

    return ExplainerScript(
        character_id=character.id,
        topic=topic,
        full_text=text,
        word_count=word_count,
        estimated_duration_s=estimated_duration_s,
    )


def truncate_to_last_sentence(text: str, max_words: int) -> str:
    """Cut text at last sentence boundary within max_words."""
    words = text.split()
    if len(words) <= max_words:
        return text

    truncated = " ".join(words[:max_words])
    # Find the last sentence-ending punctuation
    match = re.search(r"[.!?][^.!?]*$", truncated)
    if match:
        return truncated[: match.start() + 1].strip()
    return truncated.strip()
