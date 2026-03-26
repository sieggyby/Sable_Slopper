# Local Development Setup

## Initial Setup

```bash
git clone <repo>
cd Sable_Slopper

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install package in editable mode with dev extras
pip install -e ".[dev]"

# Verify
sable --version
```

The `[dev]` extra installs `pytest`, `ruff`, and `mypy`. Optional dep groups:

| Group | Install | Needed for |
|-------|---------|-----------|
| `score` | `pip install -e ".[score]"` | `scripts/score_brainrot.py` (librosa, opencv-python, numpy) |
| `local-tts` | `pip install -e ".[local-tts]"` | `character-explainer` with `--tts-backend local` (F5-TTS) |

## API Keys

Set environment variables (or run `sable config set`) before using any feature that calls external APIs:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."       # required for most features
export SOCIALDATA_API_KEY="..."             # required for pulse meta / pulse track
export REPLICATE_API_TOKEN="r8_..."         # required for face swap
export ELEVENLABS_API_KEY="..."             # required for character-explainer (elevenlabs backend)
```

For testing without touching your real config, set `SABLE_HOME` to a temp dir:

```bash
export SABLE_HOME=/tmp/sable_dev
sable config set anthropic_api_key $ANTHROPIC_API_KEY
```

See `docs/ENV_VARS.md` for the full variable reference.

## Running Tests

```bash
# All tests
pytest

# Single module
pytest tests/test_pulse_meta.py

# With output
pytest -s

# Stop on first failure
pytest -x
```

### Mocking patterns

Most external API calls (SocialData, Anthropic, Replicate) are mocked at the module boundary. Look for `conftest.py` and `@pytest.fixture` patterns in `tests/`. The test DB uses an in-memory SQLite connection — no temp files needed.

If a test touches the filesystem (vault init, profile creation), it uses `tmp_path` from pytest fixtures.

## Linting and Type Checking

```bash
# Lint + auto-fix
ruff check . --fix
ruff format .

# Type check
mypy sable/
```

The `ruff` config is in `pyproject.toml`. Mypy runs in strict mode for `sable/pulse/` and lenient mode elsewhere — check `pyproject.toml` for per-module overrides.

## Adding a New CLI Command

1. Create `sable/<module>/cli.py` with a `@click.group()` or `@click.command()`.
2. Register it in `sable/cli.py`:
   ```python
   from sable.my_module.cli import my_group
   main.add_command(my_group)
   ```
3. Add tests under `tests/test_<module>.py`.
4. Update `README.md` and the modules table.

## Database Migrations

There are two SQLite databases:

| File | Location | Contains |
|------|---------|---------|
| `pulse.db` | `$SABLE_HOME/pulse.db` | Tweet performance data, posting log, roster |
| `meta.db` | `$SABLE_HOME/meta.db` | Watchlist tweet cache, baselines, cursors |

Schema is defined in `sable/db/` and applied via `db.init_db()` on first run. If you add a column, add a migration in `sable/db/migrations.py` — the migration runner checks the current schema version on startup.

There is no Alembic or external migration tool; migrations are hand-written SQL in the `migrations` dict keyed by version number.

## File Layout

```
sable/
├── cli.py                  # Main entry point, registers all subcommands
├── config.py               # Config loading, defaults, env var overrides
├── db/                     # SQLite connection + schema + migrations
├── pulse/
│   ├── cli.py              # sable pulse group
│   └── meta/               # pulse meta subsystem
│       ├── cli.py          # sable pulse meta commands
│       ├── scanner.py      # SocialData fetching + cursor management
│       ├── fingerprint.py  # 8-bucket format classifier
│       ├── normalize.py    # Author-relative lift computation
│       ├── baselines.py    # 30d/7d baseline storage
│       ├── quality.py      # Confidence grading
│       ├── trends.py       # Trend + momentum classification
│       ├── topics.py       # Term extraction + ngram analysis
│       └── watchlist.py    # Watchlist CRUD + health diagnostics
├── vault/                  # Content vault operations
├── clip/                   # Video clip pipeline
├── meme/                   # Meme generation
├── face/                   # Face swap
├── character_explainer/    # Explainer video generation
└── roster/                 # Account + profile management
```
