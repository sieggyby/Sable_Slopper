# Sable Slopper

High-volume crypto Twitter content production toolkit. CLI-driven, Claude-powered.

## Modules

| Command | Description |
|---------|-------------|
| `sable roster` | Account management + markdown profile system |
| `sable clip` | Video → vertical clips with brainrot + captions |
| `sable meme` | Template-based meme generation |
| `sable face` | Replicate-powered face swap |
| `sable pulse` | Performance tracking + AI recommendations |

## Quick Start

```bash
pip install -e .

# Configure API keys
sable config set anthropic_api_key sk-ant-...
sable config set replicate_api_key r8_...
sable config set socialdata_api_key ...

# Add an account
sable roster add @tig_intern --display-name "Tig Intern" --org "Sable" --archetype "degen analyst"

# Edit the profile (tone, interests, context, ops notes)
sable roster profile edit @tig_intern --file tone
sable roster profile edit @tig_intern --file interests

# Show full account + profile preview
sable roster show @tig_intern
```

## Per-Account Profile Files

Each account gets a profile directory at `~/.sable/profiles/@handle/`:

```
~/.sable/profiles/
└── @tig_intern/
    ├── tone.md        # Voice, language patterns, what to avoid
    ├── interests.md   # Topics, crypto sub-communities, current meta
    ├── context.md     # Background, community standing, lore
    └── notes.md       # What's landed, what flopped, current arcs
```

All tools that call Claude (`clip`, `meme`, `pulse recommend`) auto-load these files and inject them into prompts.

```bash
sable roster profile init @handle      # Scaffold blank files
sable roster profile show @handle      # Print all profile files
sable roster profile edit @handle --file tone   # Open in $EDITOR
```

## Clip

```bash
# Process a video into 3 vertical clips
sable clip process interview.mp4 --account @tig_intern

# Dry run — show what Claude would select
sable clip process interview.mp4 --account @tig_intern --dry-run

# Add brainrot videos to library
sable clip brainrot add subway_surfers.mp4 --energy medium
```

## Meme

```bash
sable meme list-templates
sable meme generate --account @tig_intern --template drake --topic "l2 fees"
sable meme generate --account @tig_intern --dry-run  # auto-selects template
sable meme batch --account @tig_intern --count 5 --render
```

## Face

```bash
# Add reference face with consent
sable face library add photo.jpg --name tig --consent

# Swap face
sable face swap target.jpg --account @tig_intern --dry-run
sable face swap viral_clip.mp4 --account @tig_intern --quality medium
```

## Pulse

```bash
# Track performance (--mock for testing without API key)
sable pulse track --account @tig_intern --mock

# View performance report
sable pulse report --account @tig_intern --followers 15000

# Get AI recommendations
sable pulse recommend --account @tig_intern --update-roster

# Export data
sable pulse export --account @tig_intern --format csv --output report.csv
```

## Workspace

Default output location: `~/sable-workspace/output/@handle/`

Override: `export SABLE_WORKSPACE=/path/to/workspace`
