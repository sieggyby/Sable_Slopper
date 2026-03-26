# Environment Variable Reference

## API Keys

These can be set as environment variables or via `sable config set <key> <value>`. Environment variables take precedence over `~/.sable/config.yaml`.

| Variable | Config key | Required for | Default |
|----------|-----------|-------------|---------|
| `ANTHROPIC_API_KEY` | `anthropic_api_key` | All Claude-powered features (`clip`, `meme`, `pulse recommend`, `pulse meta` analysis) | — |
| `REPLICATE_API_TOKEN` | `replicate_api_key` | `sable face` (Replicate-hosted face swap models) | — |
| `SOCIALDATA_API_KEY` | `socialdata_api_key` | `sable pulse meta` (tweet fetching), `sable pulse track`, `sable pulse trends` | — |
| `ELEVENLABS_API_KEY` | *(set on character profile)* | `sable character-explainer` with `--tts-backend elevenlabs` | — |

`ELEVENLABS_API_KEY` is read directly from the environment; it is not stored in `config.yaml`.

## Path Overrides

| Variable | Purpose | Default |
|----------|---------|---------|
| `SABLE_HOME` | Override the `.sable` config directory. Useful in tests to avoid writing to your real config/watchlist/DB. | `~/.sable/` |
| `SABLE_WORKSPACE` | Override the output workspace directory for clips and memes. | `~/sable-workspace/` |

### Using SABLE_HOME for local dev / testing

Set `SABLE_HOME` to a temp directory so test runs don't pollute your real config or pulse databases:

```bash
export SABLE_HOME=/tmp/sable_test
sable config set anthropic_api_key sk-ant-...   # writes to /tmp/sable_test/config.yaml
sable pulse meta scan --org test_org            # uses /tmp/sable_test/meta.db
```

This is essential when running integration tests — without it, the test suite writes to your production `pulse.db` and `meta.db`.

## Shell / Editor

| Variable | Used by | Notes |
|----------|--------|-------|
| `EDITOR` | `sable roster profile edit` | Falls back to `vi` if unset |

## Cross-Tool Variables (SableTracking)

These vars belong to SableTracking (`app/platform_sync.py`), not to the sable CLI,
but they reference `sable.db` and are documented here for cross-tool clarity.

| Variable | Purpose | Default |
|----------|---------|---------|
| `SABLE_CLIENT_ORG_MAP` | JSON object mapping SableTracking client names → sable.db org_ids. Example: `{"TIG":"tig"}` | `{}` (sync raises `ORG_MAPPING_ERROR` if empty) |

## Example shell configuration

```bash
# ~/.zshrc or ~/.bashrc
export ANTHROPIC_API_KEY="sk-ant-..."
export REPLICATE_API_TOKEN="r8_..."
export SOCIALDATA_API_KEY="sd_..."
export ELEVENLABS_API_KEY="el_..."

# Optional overrides
export SABLE_WORKSPACE="$HOME/work/sable-output"
```
