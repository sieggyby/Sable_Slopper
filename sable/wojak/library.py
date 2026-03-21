"""Wojak asset library — load, query, and register wojak PNGs."""
from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path
from typing import Optional

import yaml

from sable.shared.paths import wojaks_dir

_LIBRARY_FILE = "_library.yaml"

_DEFAULT_LIBRARY: list[dict] = []  # populated below

_SEED_LIBRARY = [
    {
        "id": "crying-wojak",
        "name": "Crying Wojak",
        "emotion": "sad",
        "tags": ["crying", "sad", "tears", "feels", "loss", "pain"],
        "description": "Classic crying face. Use for loss, despair, or relatable pain.",
        "image_file": "crying_wojak.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG15.png",
        "transparent": True,
        "dimensions": [500, 500],
    },
    {
        "id": "doomer-wojak",
        "name": "Doomer Wojak",
        "emotion": "doomer",
        "tags": ["doomer", "black hoodie", "existential", "dread", "hopeless", "night"],
        "description": "Black hoodie, cigarette, existential dread. Use for nihilism, late-night despair, bearish sentiment.",
        "image_file": "doomer_wojak.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG17.png",
        "transparent": True,
        "dimensions": [500, 600],
    },
    {
        "id": "coomer-wojak",
        "name": "Coomer Wojak",
        "emotion": "obsessed",
        "tags": ["coomer", "addicted", "obsessed", "compulsive", "degenerate"],
        "description": "Hollow-eyed, addicted expression. Use for obsessive behavior, compulsive trading, degen energy.",
        "image_file": "coomer_wojak.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG18.png",
        "transparent": True,
        "dimensions": [500, 500],
    },
    {
        "id": "npc-wojak",
        "name": "NPC Wojak",
        "emotion": "blank",
        "tags": ["npc", "blank", "no inner monologue", "grey", "mindless", "herd"],
        "description": "Grey face, blank expression, no inner monologue. Use for groupthink, herd behavior, normie takes.",
        "image_file": "npc_wojak.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG20.png",
        "transparent": True,
        "dimensions": [500, 500],
    },
    {
        "id": "chad-wojak",
        "name": "Chad Wojak",
        "emotion": "chad",
        "tags": ["chad", "confident", "strong jaw", "unbothered", "alpha", "based"],
        "description": "Tall, strong jaw, eyes closed, confident. Use for chad energy, unbothered takes, alpha moves.",
        "image_file": "chad_wojak.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG22.png",
        "transparent": True,
        "dimensions": [400, 700],
    },
    {
        "id": "boomer-wojak",
        "name": "Boomer Wojak",
        "emotion": "smug",
        "tags": ["boomer", "smug", "worked hard", "back in my day", "ok boomer"],
        "description": "'I did it by working hard' energy. Use for out-of-touch advice, meritocracy takes.",
        "image_file": "boomer_wojak.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG24.png",
        "transparent": True,
        "dimensions": [500, 500],
    },
    {
        "id": "zoomer-wojak",
        "name": "Zoomer Wojak",
        "emotion": "anxious",
        "tags": ["zoomer", "headphones", "detached", "gen z", "anxious", "ironic"],
        "description": "Headphones, detached expression. Use for Gen Z irony, detached anxiety, ADHD energy.",
        "image_file": "zoomer_wojak.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG25.png",
        "transparent": True,
        "dimensions": [500, 550],
    },
    {
        "id": "wojak-pointing",
        "name": "Wojak Pointing",
        "emotion": "accusatory",
        "tags": ["pointing", "accusatory", "calling out", "that guy", "notice"],
        "description": "Pointing finger, accusatory expression. Use for calling something out or identifying a type.",
        "image_file": "wojak_pointing.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG26.png",
        "transparent": True,
        "dimensions": [500, 500],
    },
    {
        "id": "wojak-smug",
        "name": "Smug Wojak",
        "emotion": "smug",
        "tags": ["smug", "slight smile", "knowing", "i told you so", "got it"],
        "description": "Slight smug smile. Use for 'I told you so' moments, subtle superiority, knowing looks.",
        "image_file": "wojak_smug.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG27.png",
        "transparent": True,
        "dimensions": [500, 500],
    },
    {
        "id": "brainlet-wojak",
        "name": "Brainlet Wojak",
        "emotion": "dumb",
        "tags": ["brainlet", "small brain", "drooling", "dumb", "smooth brain", "low iq"],
        "description": "Tiny head, drooling expression. Use for bad takes, low-IQ reasoning, smooth-brain logic.",
        "image_file": "brainlet_wojak.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG28.png",
        "transparent": True,
        "dimensions": [500, 550],
    },
    {
        "id": "big-brain-wojak",
        "name": "Big Brain Wojak",
        "emotion": "overconfident",
        "tags": ["big brain", "galaxy brain", "huge head", "overconfident", "galaxy"],
        "description": "Enormous head, overconfident. Use for galaxy-brain takes, overcomplicated logic, 200 IQ plays.",
        "image_file": "big_brain_wojak.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG29.png",
        "transparent": True,
        "dimensions": [600, 600],
    },
    {
        "id": "mask-on-wojak",
        "name": "Mask-On Wojak",
        "emotion": "fake",
        "tags": ["mask", "fake", "smiling outside", "crying inside", "cope", "pretending"],
        "description": "Smiling mask over crying face. Use for coping, fake optimism, performative positivity.",
        "image_file": "mask_on_wojak.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG30.png",
        "transparent": True,
        "dimensions": [500, 500],
    },
    {
        "id": "two-wojaks-arguing",
        "name": "Two Wojaks Arguing",
        "emotion": "conflict",
        "tags": ["arguing", "conflict", "debate", "two sides", "disagreement"],
        "description": "Pre-built two-character scene with two wojaks facing off. Use for internal conflict or two-sided debates.",
        "image_file": "two_wojaks_arguing.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG31.png",
        "transparent": True,
        "dimensions": [900, 500],
    },
    {
        "id": "soyjak-open-mouth",
        "name": "Soyjak Open Mouth",
        "emotion": "hype",
        "tags": ["soyjak", "soy", "open mouth", "amazed", "hype", "excited", "nerd"],
        "description": "Wide open mouth, pointing excitedly. Use for hype, over-enthusiasm, ironic amazement.",
        "image_file": "soyjak_open_mouth.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG32.png",
        "transparent": True,
        "dimensions": [500, 600],
    },
    {
        "id": "soyjak-pointing",
        "name": "Soyjak Pointing",
        "emotion": "accusatory",
        "tags": ["soyjak", "pointing", "calling out", "soy", "gotcha", "that"],
        "description": "Soyjak variant pointing at something. Use for calling out, accusatory takes, 'look at this'.",
        "image_file": "soyjak_pointing.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG33.png",
        "transparent": True,
        "dimensions": [500, 600],
    },
    {
        "id": "tradwife-wojak",
        "name": "Tradwife Wojak",
        "emotion": "nostalgic",
        "tags": ["tradwife", "traditional", "nostalgic", "domestic", "contrast"],
        "description": "Traditional, wholesome expression. Use for nostalgic contrast, trad-vs-modern commentary.",
        "image_file": "tradwife_wojak.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG34.png",
        "transparent": True,
        "dimensions": [450, 600],
    },
    {
        "id": "wojak-suit",
        "name": "Wojak in Suit",
        "emotion": "professional",
        "tags": ["suit", "business", "professional", "corporate", "formal", "linkedin"],
        "description": "Business wojak in a suit. Use for corporate takes, professional irony, LinkedIn energy.",
        "image_file": "wojak_suit.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG35.png",
        "transparent": True,
        "dimensions": [500, 700],
    },
    {
        "id": "feels-good-man",
        "name": "Feels Good Man",
        "emotion": "satisfied",
        "tags": ["feels good", "satisfied", "comfy", "cozy", "pepe", "happy", "winning"],
        "description": "Classic 'feels good man' expression. Use for satisfaction, winning moments, comfy energy.",
        "image_file": "feels_good_man.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG36.png",
        "transparent": True,
        "dimensions": [500, 500],
    },
    {
        "id": "depression-wojak",
        "name": "Depression Wojak",
        "emotion": "depressed",
        "tags": ["depression", "lying down", "bed", "no motivation", "empty", "hollow"],
        "description": "Lying in bed, hollow expression. Use for paralysis, motivation loss, bearish doom energy.",
        "image_file": "depression_wojak.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG37.png",
        "transparent": True,
        "dimensions": [600, 400],
    },
    {
        "id": "average-enjoyer",
        "name": "Average Enjoyer",
        "emotion": "neutral",
        "tags": ["average", "enjoyer", "neutral", "just vibing", "normal", "baseline"],
        "description": "'Average X enjoyer' format. Neutral baseline character. Use for the 'average enjoyer vs. X enjoyer' format.",
        "image_file": "average_enjoyer.png",
        "source_url": "https://pngimg.com/uploads/memes/memes_PNG38.png",
        "transparent": True,
        "dimensions": [500, 600],
    },
]


def _library_path() -> Path:
    return wojaks_dir() / _LIBRARY_FILE


def _ensure_library() -> None:
    path = _library_path()
    if not path.exists():
        with open(path, "w") as f:
            yaml.dump(_SEED_LIBRARY, f, default_flow_style=False, allow_unicode=True)


def load_library() -> list[dict]:
    _ensure_library()
    with open(_library_path()) as f:
        data = yaml.safe_load(f) or []
    return data if isinstance(data, list) else []


def get_wojak(wojak_id: str) -> dict:
    library = load_library()
    for w in library:
        if w["id"] == wojak_id:
            return w
    raise ValueError(
        f"Wojak '{wojak_id}' not found. "
        f"Available: {', '.join(w['id'] for w in library)}"
    )


def get_wojak_image(wojak: dict) -> Optional[Path]:
    """Return path to wojak PNG or None if not downloaded."""
    img_file = wojak.get("image_file", "")
    path = wojaks_dir() / img_file
    return path if path.exists() else None


def add_wojak(
    url: str,
    wojak_id: str,
    name: str,
    emotion: str,
    tags: list[str],
    description: str,
) -> dict:
    """Download a wojak PNG and register it in the library."""
    library = load_library()

    # Check for duplicate
    for w in library:
        if w["id"] == wojak_id:
            raise ValueError(f"Wojak ID '{wojak_id}' already exists in library.")

    # Determine filename from URL
    suffix = Path(url).suffix or ".png"
    image_file = f"{wojak_id.replace('-', '_')}{suffix}"
    dest = wojaks_dir() / image_file

    # Download
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception as e:
        raise RuntimeError(f"Failed to download {url}: {e}")

    # Validate transparency
    try:
        from PIL import Image
        img = Image.open(dest)
        transparent = img.mode in ("RGBA", "LA") or (
            img.mode == "P" and "transparency" in img.info
        )
    except Exception:
        transparent = suffix.lower() == ".png"

    if not transparent:
        dest.unlink(missing_ok=True)
        raise ValueError(
            f"Image at {url} does not appear to be transparent. "
            "Wojak compositor requires transparent PNGs."
        )

    try:
        dimensions = list(img.size)
    except Exception:
        dimensions = [500, 500]

    entry = {
        "id": wojak_id,
        "name": name,
        "emotion": emotion,
        "tags": tags,
        "description": description,
        "image_file": image_file,
        "source_url": url,
        "transparent": True,
        "dimensions": dimensions,
    }

    library.append(entry)
    with open(_library_path(), "w") as f:
        yaml.dump(library, f, default_flow_style=False, allow_unicode=True)

    return entry


def download_missing(verbose: bool = False) -> dict[str, bool]:
    """Try to download any library entries that are missing their image file."""
    library = load_library()
    results: dict[str, bool] = {}

    for entry in library:
        img_path = wojaks_dir() / entry.get("image_file", "")
        if img_path.exists():
            results[entry["id"]] = True
            continue

        url = entry.get("source_url", "")
        if not url:
            results[entry["id"]] = False
            continue

        try:
            urllib.request.urlretrieve(url, img_path)
            results[entry["id"]] = True
            if verbose:
                print(f"  ✓ Downloaded {entry['id']}")
        except Exception as e:
            results[entry["id"]] = False
            if verbose:
                print(f"  ✗ Failed {entry['id']}: {e}")

    return results
