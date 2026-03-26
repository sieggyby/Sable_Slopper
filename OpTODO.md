# OpTODO — Operator Task Queue

Day-to-day operational tasks: client setup, content production, data hygiene.
Not code fixes — see `TODO.md` for that.

---

## TIG — Full Platform Setup

### 1. Fill `@tigfoundation` profiles
**Files:** `~/.sable/profiles/@tigfoundation/tone.md`, `interests.md`, `context.md`, `notes.md`
All four files are blank templates. Fill before using any TIG tools — affects content generation,
vault context, and `sable write` for that account.

### 2. Register TIG org in sable.db
```bash
sable org create TIG
```
Required for platform layer: jobs, cost tracking, entity sync, vault platform sync.

### 3. Fix TIG watchlist
**File:** `~/.sable/pulse/watchlist.yaml` → `orgs.tig` section
Currently has `@example` as placeholder. Replace with 5–10 real accounts from TIG's niche:
intellectual/research-side crypto CT, AI-meets-crypto, tacit knowledge / incentive structure
discourse. These drive format intelligence for `sable write` and `sable pulse account`.

### 4. Process any remaining source videos
Run `sable clip process` on any Fletcher interviews or TIG-relevant videos not yet processed.
Current corpus: 18 clips across 3 interviews. Better to have the full corpus before vault
sync than to add piecemeal.

### 5. Run pulse meta scan
```bash
sable pulse meta scan --org TIG
```
meta.db is currently empty — no niche scan has run. Needed for format intelligence,
`sable write` auto-format selection, and `sable pulse account` divergence column.

### 6. Vault sync
```bash
sable vault sync --org TIG
```
No vault exists yet for TIG. Run after steps 1–5 so the vault is built on a complete corpus.

### 7. Vault enrich
```bash
sable vault enrich --org TIG
```
Annotates vault notes with topics, questions answered, tone, depth, keywords.
Run after sync.

---
