# Migrations

These SQL migration files (001–006) are the historical Slopper-era migrations for `sable.db`.

**Migrations are now owned by SablePlatform.**

Going forward, all new schema changes must be added to
`/Users/sieggy/Projects/SablePlatform/sable_platform/db/migrations/`
and the `_MIGRATIONS` list in `sable_platform/db/connection.py`.

`sable.platform.db.ensure_schema()` is a thin re-export of
`sable_platform.db.connection.ensure_schema`, so migration application is
handled entirely by SablePlatform at runtime. The files in this directory
are kept for historical reference only and are no longer executed.
