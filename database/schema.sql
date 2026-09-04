-- Module 5: RDS metadata schema (PostgreSQL).
-- File CONTENTS are not stored here.  S3 holds bytes; these tables hold metadata.
-- Applied automatically by SQLAlchemy create_all / python -m backend.rds_setup.

CREATE TABLE IF NOT EXISTS files (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(512) NOT NULL,
    relative_path VARCHAR(1024) NOT NULL,
    current_version INTEGER NOT NULL DEFAULT 0,
    current_hash VARCHAR(64),
    size INTEGER,
    status VARCHAR(32) NOT NULL DEFAULT 'synced',
    -- M8 may set status to 'conflict' on the cloud-canonical file while a
    -- sibling *.conflict-<hash>.* path stores the other side's bytes.
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    storage_key VARCHAR(1024),
    storage_version_id VARCHAR(256),
    CONSTRAINT uq_files_relative_path UNIQUE (relative_path)
);

CREATE TABLE IF NOT EXISTS file_versions (
    id SERIAL PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files (id),
    version_number INTEGER NOT NULL,
    hash VARCHAR(64),
    size INTEGER,
    operation VARCHAR(32) NOT NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'local',
    storage_version_id VARCHAR(256),
    created_at VARCHAR(32) NOT NULL
    -- M8: conflict copies use operation='CONFLICT' and files.status='conflict'.
    -- No extra table is required; previous versions remain in this table.
);

CREATE INDEX IF NOT EXISTS ix_file_versions_file_id ON file_versions (file_id);

CREATE TABLE IF NOT EXISTS sync_logs (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES files (id),
    path VARCHAR(1024) NOT NULL,
    operation VARCHAR(32) NOT NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'local',
    destination VARCHAR(64) NOT NULL DEFAULT 'backend',
    status VARCHAR(32) NOT NULL,
    error_message TEXT,
    timestamp VARCHAR(32) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sync_logs_file_id ON sync_logs (file_id);
CREATE INDEX IF NOT EXISTS ix_sync_logs_timestamp ON sync_logs (timestamp);

CREATE TABLE IF NOT EXISTS sync_changes (
    id SERIAL PRIMARY KEY,
    file_id INTEGER REFERENCES files (id),
    path VARCHAR(1024) NOT NULL,
    dest_path VARCHAR(1024),
    operation VARCHAR(32) NOT NULL,
    hash VARCHAR(64),
    size INTEGER,
    version_number INTEGER,
    timestamp VARCHAR(32) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sync_changes_file_id ON sync_changes (file_id);
CREATE INDEX IF NOT EXISTS ix_sync_changes_timestamp ON sync_changes (timestamp);
