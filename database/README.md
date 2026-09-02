# Database

Module 5 stores relational **metadata** here, not file bytes.

- `schema.sql` — PostgreSQL reference schema (`files`, `file_versions`, `sync_logs`, `sync_changes`)
- Runtime creation: `python -m backend.rds_setup` (SQLAlchemy `create_all`)

See `modules/module-05/README.md` for configuration and AWS setup.
