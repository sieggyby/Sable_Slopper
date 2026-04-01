# TODO

---

## Validation Snapshot

- `./.venv/bin/python -m pytest -q` → `569 passed`
- `./.venv/bin/ruff check .` → 0
- `./.venv/bin/mypy sable` → 0

---

## Structural Debt

### AI spend observability gap

Non-org Claude call sites (content generation flows like clip/thumbnail/write without
`--org`) remain intentionally budget-exempt. Spend is not observable in a single place
for these flows. Org-scoped advise/meta paths are fully gated.

**When to fix:** When a second active client makes cost attribution important.

### Stale test schemas

Some tests still encode stale producer/consumer schemas that don't match the live
contracts. Lint and mypy are clean; the issue is semantic correctness of test fixtures.

### Handle normalization duplication

Handle normalization (strip `@`, lowercase) is inline at 20+ sites. A tracked TODO
comment exists at `sable/advise/stage1.py` (`_norm_handle`). Consolidation into
`sable/shared/utils.py::normalize_handle()` deferred — low risk, cosmetic value only.

---

## FEATURE-3 (`sable pulse account`) — Remaining Items

- **`_classify_post` thread-detection gap** (known V1 limitation): `sable_content_type='text'`
  always passes `is_thread=False` because pulse.db has no thread marker. Text threads
  miscategorized as `standalone_text`. Requires pulse.db schema change to fix.

---

## Clip Pipeline Upgrades

Sourced from competitive audit of `samuraigpt/ai-youtube-shorts-generator` (2026-04-01).

### CLIP-2 · Face-centered crop for multi-speaker content

Current `stack_videos` (`shared/ffmpeg.py`) uses a static `scale+crop` filter that
center-crops the source panel. For interview content where speakers switch sides of
frame, a face-tracking crop would keep the largest detected face centered.

**Clarification:** This is face-centered cropping, not active-speaker detection. True
speaker identification would require audio diarization (pyannote) or lip-movement
analysis — neither is in scope. This tracks the largest face per frame.

**Approach:** Face detection (dlib HOG via `face_recognition`) every 10th frame (~3fps),
interpolated positions for intermediate frames. Smoothed crop x-offset via exponential
smoothing (e.g. 0.85 previous + 0.15 new). FFmpeg `crop` filter with per-frame offset.

**Dependency:** `face_recognition` is currently an optional import with try/except
fallback in `thumbnail.py`. It is NOT a declared dependency in `pyproject.toml` (dlib
requires CMake + C++ toolchain). Decision needed: (a) declare it as a hard dep, or
(b) keep optional and fall back to center-crop when unavailable. Option (b) is safer.

**Where it lives:** Detection + smoothing logic in new `sable/clip/face_track.py` (not
`shared/ffmpeg.py` — that module is pure FFmpeg subprocess wrappers). Only the final
crop-filter generation touches `ffmpeg.py`. Called from `assembler.py` when `--face-track`
flag is passed. Default off — static crop remains the default.

**Applies to:** Both `stack_videos` and `encode_clip_only` paths. Ignored when
`--audio-only` is set (no source video panel to crop).

**Edge cases:**
- Zero faces for entire clip → fall back to center crop
- Face appears/disappears mid-clip → hold last known position, decay to center
- Multiple faces → track largest, or nearest to previous position
- Performance budget: ~1-2x assembly time overhead at 720p with dlib HOG at 3fps

**When to build:** When a client asks for interview/podcast clip quality improvements, or
when we start processing multi-camera content. Build CLIP-2 before CLIP-3 (CLIP-3
depends on CLIP-2's detection gate).

### CLIP-3 · Motion-tracking crop for screen recordings

**Prerequisite: CLIP-2.** CLIP-3 is the no-face fallback within CLIP-2's `--face-track`
path. Cannot be built or used independently.

When `--face-track` is on and face detection returns no faces (screen shares, product
demos, coding streams), the current pipeline would center-crop. An optical-flow-based
crop would instead pan toward the area of activity (mouse cursor, typing, UI transitions).

**Approach:** Farneback optical flow (`cv2.calcOpticalFlowFarneback`, `opencv-python` is
a declared dep) computed once per second. Per-column flow magnitude summed → weighted
center of motion → smoothed pan position. Source scaled so its width is 1.5x the output
panel width (after the existing `scale` filter in the FFmpeg graph), giving 0.25x
panel-width of pan room in each direction.

**Where it lives:** Alongside CLIP-2 in `sable/clip/face_track.py`.

**Edge cases:**
- First frame: no prior frame for flow → default to center crop
- Static frames (no significant flow): hold current pan position, do not drift to center.
  Define a flow-magnitude threshold below which pan is frozen
- Full-screen transitions (page nav, app switch): flow spikes everywhere with no
  directional signal → treat as static, hold position

**Performance:** Farneback on 1080p ~50-100ms/frame on CPU. At 1fps for a 30s clip =
~1.5-3s overhead. Consider downscaling to 540p for flow computation.

**When to build:** When we start clipping screen-share or product demo content.

---

## Phase 2+ (Deferred)

### Phase 2 — Web UI (`sable serve`)

- FastAPI app in `sable/serve/app.py`
- Cloudflare Tunnel for team/client access
- Role-based access control via `sable/vault/permissions.py` (currently stub)
- Token auth middleware + `~/.sable/vault_users.yaml`
- Web views: dashboard, content browser, search, reply suggest, posting log
- See `docs/ROLES.md` for permission matrix, `docs/ROADMAP.md` for architecture

### Phase 3 — VPS

- Docker + systemd, Postgres backend, multi-org S3 vault storage
- Webhook receivers for pulse data push + tweet notifications
- Scheduled sync via cron

### Phase 4 — Scale

- Multi-tenant auth, vault-as-API, real-time enrichment queue (Celery/Redis)
- Automated gap-fill suggestions triggered by pulse performance data
- Client portal with read-only dashboard + export access

---

## Convention Notes for Future Feature Work

### Command registration

- Top-level commands in `sable/cli.py`; nested subcommands in owning group file
- Handle-scoped commands call `require_account()` first; default `--org` from roster
- `build_account_context()` takes an `Account` object, not a bare handle string

### DB schema awareness

- `pulse.db` uses `posts.id` and `snapshots.id` (not `post_id`/`snapshot_id`)
- `posts.sable_content_type` is a coarse hint, not a format taxonomy — map to
  pulse-meta format buckets explicitly
- `meta.db.format_baselines` stores baseline aggregates only (no `current_lift`,
  `status`, `momentum`, `confidence_grade`)
- `load_all_notes()` returns frontmatter dicts with `_note_path`; scans
  `vault/content/**/*.md` only
- Vault note lifecycle: `posted_by` and `suggested_for` — no `status='posted'` field
- Content note freshness: `assembled_at` (no `created_at` on synced content notes)
- Config access: `sable.config.get(...)` / `require_key(...)` (no `get_config()`)
- `search_vault(query, vault_path, org, filters=SearchFilters(...), config=...)`

### Shared patterns

- Claude calls via `call_claude()` / `call_claude_json()` from `sable/shared/api.py`
- Org-scoped calls pass `org_id` + `call_type`; non-org sites annotated `# budget-exempt`
- File writes via `atomic_write()` from `sable/shared/files.py`
- All `except Exception` blocks must `logger.warning(...)` — no silent swallows
- New modules follow: `__init__.py`, main logic file, CLI command, tests in `tests/{module}/`
- `pulse/meta` DB changes go in `_SCHEMA` string (not migration files)

### Validation checklist

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/ruff check .
./.venv/bin/mypy sable
```
