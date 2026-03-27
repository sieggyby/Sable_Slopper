CREATE TABLE IF NOT EXISTS discord_pulse_runs (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id                TEXT NOT NULL,
    project_slug          TEXT NOT NULL,
    run_date              TEXT NOT NULL,           -- ISO date YYYY-MM-DD
    wow_retention_rate    REAL,                    -- NULL on first pulse run (no prior window)
    echo_rate             REAL,
    avg_silence_gap_hours REAL,
    weekly_active_posters INTEGER,
    retention_delta       REAL,                    -- NULL on first run
    echo_rate_delta       REAL,                    -- NULL on first run
    created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (org_id, project_slug, run_date)
);

CREATE INDEX IF NOT EXISTS idx_discord_pulse_runs_org_date
    ON discord_pulse_runs (org_id, run_date);

UPDATE schema_version SET version = 6 WHERE version < 6;
