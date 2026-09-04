# Module 08 — Versioning & Conflict Handling

## 1. Overview and Responsibility

Module 08 implements file versioning, recoverable historical versions, and deterministic conflict detection and preservation across the hybrid cloud synchronization framework.

The primary architectural guarantee of Module 08 is **Zero Silent Overwrite**: when concurrent or divergent modifications occur on the local filesystem and the cloud backend, neither version is discarded or overwritten. Both copies are preserved, cataloged, logged, and made available for inspection and resolution.

---

## 2. Integration with Existing Foundations

Module 08 directly builds upon and extends the existing architecture established in M1–M7 without redesigning or rebuilding:

- **Amazon S3 Object Versioning (M4):**
  - Uses the existing S3 storage adapter (`S3FileStorage` and `MemoryFileStorage`).
  - Stores each version's payload in S3, capturing the S3 `VersionId`.
  - Extended `FileStorage.get(key, version_id)` to allow retrieving specific historical versions via AWS S3 `GetObject(..., VersionId=...)`.

- **Amazon RDS Metadata Repository (M5):**
  - Reuses the existing relational schema: `files`, `file_versions`, `sync_logs`, and `sync_changes`.
  - Increments `files.current_version` on modification and tracks `files.current_hash`.
  - Records every version in `file_versions` with `version_number`, `hash`, `size`, `operation`, `source`, `storage_version_id`, `created_at`, and `is_conflict`.
  - Marks conflicting canonical files with `status = 'conflict'` using `set_file_status()`.
  - Logs conflict events to `sync_logs` with `operation = 'CONFLICT'` and diagnostic messages.
  - Publishes conflict copies to `sync_changes` (`operation = 'CREATED'`) so remote synchronization agents discover the conflict copy.

- **Bidirectional Synchronization & State (M7):**
  - Integrates with `agent/state.py` (`SyncState`), `agent/watcher.py`, and `agent/poller.py` (`CloudPoller`).
  - Propagates `base_hash` from `SyncState` during local event dispatch to enable 3-way conflict detection.
  - `CloudPoller` detects local divergent modifications during cloud pull operations and creates local conflict copies before applying cloud changes.

---

## 3. Versioning Strategy & Persistence

### 3.1 Normal File Modification
When an existing file is modified:
1. The client computes the new SHA-256 hash and sends the upload request with `operation="MODIFIED"`, `hash`, and the last known synced hash (`base_hash`).
2. The backend identifies the existing logical file record in RDS by its relative path (`upsert_file`).
3. If the content hash matches the existing record, the request is recognized as **idempotent** and returns `idempotent=True` without creating duplicate versions.
4. The new content is written to S3 via `storage.put()`, generating a new S3 `VersionId`.
5. RDS increments `current_version`, updates `current_hash`, and appends an entry to `file_versions`.
6. A success entry is appended to `sync_logs` and `sync_changes`.

### 3.2 Historical Version Recovery
Historical versions remain identifiable and downloadable:
- **List Version History:** `GET /files/{file_id}/versions` returns all versions for the file in ascending version sequence.
- **Download Historical Content:** `GET /files/{file_id}/content?version={version_number}` queries `file_versions` for the corresponding `storage_version_id` and retrieves the exact bytes from storage.

---

## 4. Conflict Handling Strategy

### 4.1 Conflict Detection (3-Way Divergence)
A conflict is detected deterministically when:
```text
local_hash != cloud_hash AND base_hash != cloud_hash AND base_hash != local_hash
```
This distinguishes genuine concurrent edits from standard sequential modifications (where `base_hash == cloud_hash`).

### 4.2 Conflict Preservation
When a conflict is detected:
1. **Canonical File Preserved:** The original path retains the cloud-canonical bytes and version history. Its status in the `files` table is updated to `'conflict'`.
2. **Deterministic Conflict Copy:** The conflicting local content is saved to S3 and RDS under a deterministic sibling path:
   ```text
   {parent_dir}/{filename_stem}.conflict-{local_hash[:12]}.{extension}
   ```
   *Example:* `reports/summary.txt` -> `reports/summary.conflict-a1b2c3d4e5f6.txt`
3. **Metadata & Versioning:**
   - A new logical file is registered in `files` for the conflict copy path.
   - An entry in `file_versions` is added with `operation = 'CONFLICT'`, `source = 'local'`, and `is_conflict = True`.
4. **Audit Logging:**
   - Two `sync_logs` records are created with `operation = 'CONFLICT'`: one for the original path and one for the conflict path, detailing the diverging hashes.
5. **Change Distribution:**
   - A `sync_changes` event (`operation = 'CREATED'`) is published for the conflict path so other agents synchronize the conflict copy.
6. **Poller Handling:**
   - On the agent side, `CloudPoller` detects if a local file was modified offline relative to `SyncState`. It creates a local conflict copy before writing the incoming cloud content, ensuring neither side is lost.

---

## 5. Idempotency & Loop Prevention

- **Upload Retries:** Re-uploading identical file bytes returns `idempotent=True` with no new version created in RDS or S3.
- **Conflict Retries:** Re-sending conflicting bytes calculates the identical deterministic path (`.conflict-<hash>`); the backend identifies that the conflict copy already exists with matching hash and returns `idempotent=True` without duplicate files or versions.
- **Sync Loop Prevention:** When `CloudPoller` downloads cloud changes, it updates `SyncState` with the cloud file hash. When the local watcher inspects the newly written file, it detects `known_hash == file_hash` and suppresses local event dispatch, preventing infinite cloud -> local -> cloud ping-pong loops.

---

## 6. Verification and Test Coverage

Module 08 tests are located in `modules/module-08/tests/test_m8.py`.

### 6.1 Covered Requirements (14/14)
1. **New file creation still works:** `test_01_new_file_creation_still_works`
2. **Existing file modification creates a new version:** `test_02_existing_file_modification_creates_new_version`
3. **Previous version remains available:** `test_03_previous_version_remains_available`
4. **Version history endpoint works:** `test_04_version_history_endpoint_works`
5. **Version hashes/metadata persist correctly:** `test_05_version_hashes_and_metadata_persist_correctly`
6. **Multiple sequential modifications create multiple versions:** `test_06_multiple_sequential_modifications_create_multiple_versions`
7. **M7 bidirectional synchronization remains functional:** `test_07_m7_bidirectional_synchronization_remains_functional`
8. **Genuine conflicts are detected:** `test_08_genuine_conflicts_are_detected`
9. **Conflicts never silently overwrite either version:** `test_09_conflicts_never_silently_overwrite_either_version`
10. **Both conflicting versions remain preserved:** `test_10_both_conflicting_versions_remain_preserved`
11. **Conflict information persists:** `test_11_conflict_information_persists`
12. **Conflict events are logged:** `test_12_conflict_events_are_logged`
13. **Repeated/retried operations are idempotent:** `test_13_repeated_retried_operations_are_idempotent`
14. **No synchronization loops are introduced:** `test_14_no_synchronization_loops_are_introduced`

Additional tests cover backward compatibility with clients omitting `base_hash`, poller-side conflict preservation, and conflict naming utilities.

### 6.2 Test Command and Results
```bash
pytest modules/module-08/tests/test_m8.py -v
```
**Result:** 17 passed, 1 warning (Starlette testclient deprecation) in 1.61s.

Full project test suite:
```bash
pytest
```
**Result:** 140 passed, 2 skipped, 1 warning in 10.45s.
