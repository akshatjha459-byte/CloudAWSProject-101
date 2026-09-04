# Module 10 — Frontend Dashboard

## 1. Overview

Module 10 adds a read-only web dashboard that consumes the existing Module 3 (FastAPI) REST API. The dashboard displays system health, file metadata, synchronization logs, cloud changes, and version history.

M10 does **not** connect directly to Amazon RDS, S3, CloudWatch, or any AWS credentials. It uses only the existing M3 API endpoints.

## 2. Files

- `dashboard/index.html` — single-page dashboard shell
- `dashboard/styles.css` — responsive layout and status badges
- `dashboard/app.js` — API client, DOM rendering, and auth handling
- `modules/module-10/tests/test_m10.py` — integration/architecture guard tests

## 3. Backend Changes

### `backend/main.py`

Added a `StaticFiles` mount so the dashboard is served from the same FastAPI process:

```python
app.mount(
    "/dashboard",
    StaticFiles(directory=str(Path(__file__).resolve().parent.parent / "dashboard"), html=True),
    name="dashboard",
)
```

No new backend API endpoints were added. No existing routes were modified.

### `backend/requirements.txt`

No new dependencies were required. The installed FastAPI 0.141.1 / Starlette 1.6.0 `StaticFiles` implementation uses `anyio.to_thread.run_sync` and does not require `aiofiles`.

## 4. Consumed M3 API Endpoints

| Endpoint | Method | Dashboard Use |
|---|---|---|
| `/health` | GET | Health badge |
| `/status` | GET | System overview cards |
| `/files` | GET | File table |
| `/files/{file_id}/versions` | GET | Version history modal |
| `/files/{file_id}/content?version={n}` | GET | Download historical version |
| `/logs` | GET | Recent sync logs |
| `/sync/changes` | GET | Recent cloud changes feed |

## 5. Authentication

Protected endpoints require the `X-API-Key` header when the backend runs with `APP_ENV=production`. The dashboard:

- Prompts for the API key on first load
- Stores the key in `sessionStorage` (cleared when the browser tab closes)
- Sends `X-API-Key` on every protected request
- Shows an auth banner and re-prompts on HTTP 401

The dashboard never hardcodes an API key.

## 6. Verification

### Local development

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/dashboard/` in a browser.

### Production (EC2)

The existing `cloudaws-backend.service` systemd unit serves the dashboard at `http://<EC2-PUBLIC-IP>:8000/dashboard/` after restarting with the updated code.

### Tests

```bash
pytest modules/module-10/tests/test_m10.py -v
pytest
```

## 7. Security Notes

- The API key is visible in browser DevTools Network tab. This is acceptable for the academic demonstration scope. The backend is not intended for exposure to untrusted public users.
- The dashboard is served from the same origin as the API, so no CORS configuration is required.
- All data displayed comes from the existing M3 REST API; no AWS credentials or direct database connections are used by the frontend.
