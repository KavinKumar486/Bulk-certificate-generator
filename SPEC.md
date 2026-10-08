# Bulk Certificate Generator: Implementation Spec (5 Checkpoints)

> Instructions for an agentic coding assistant.
>
> **How to work:**
> 1. Read this entire file first. Sections 1 to 9 are the shared reference. Sections 10 onward are the checkpoints.
> 2. Implement ONE checkpoint at a time, in order (CP0 → CP4).
> 3. At the end of each checkpoint: run the listed commands, make sure every "Done when" item is true, then **STOP**. Give a short report (files created, what each does, test results) and wait for the user to say "continue" before starting the next checkpoint.
> 4. Do not build anything listed under Non-Goals. Do not pull work forward from later checkpoints.
> 5. If something in this spec is ambiguous or contradictory, ask instead of guessing.

---

## 1. Goal

Backend API that accepts a list of recipients in one request, generates one PDF certificate per valid recipient from a single predefined template, tracks status per job and per certificate, and lets the client retrieve the generated files.

This is an interview take-home. Code must be **simple, readable and easy to explain and modify**. Prefer fewer moving parts over cleverness.

## 2. Hard Requirements (from the brief)

1. Accept a bulk generation request (one request, many recipients).
2. Validate recipient data.
3. Generate a certificate per valid recipient from one predefined template.
4. Track generation status; let the client check progress/result.
5. Let the client retrieve generated certificates.
6. One certificate failing must NOT stop the others in the same job.
7. Job status must show which certificates succeeded/failed, with reasons.
8. Document the processing choice (sync vs background) and reasoning.
9. Tests covering: job creation, input validation, certificate generation, job status/progress, individual failure handling, retrieval.
10. README with setup, run, test, submit request, retrieve certificates, design decisions.

## 3. Tech Stack (fixed)

| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| Framework | FastAPI |
| ORM | SQLAlchemy 2.x |
| Database | SQLite by default; URL from env so Postgres works unchanged |
| Validation | Pydantic v2 |
| PDF | ReportLab (draw overlay) + pypdf (merge onto template) |
| Background work | FastAPI `BackgroundTasks` |
| Tests | pytest + FastAPI `TestClient` |

Do NOT use: Airflow, Celery, Redis, GCP/cloud storage, webhooks, message brokers.

## 4. Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI app, router registration, table creation on startup
│   ├── config.py          # settings from env
│   ├── auth.py            # API key dependency
│   ├── db.py              # engine, SessionLocal, Base, get_db
│   ├── models.py          # Job, Certificate
│   ├── schemas.py         # Pydantic request/response models
│   ├── constants.py       # template path, text coordinates, fonts, sizes
│   ├── routers/
│   │   └── jobs.py        # all /v1/jobs endpoints
│   └── services/
│       ├── job_service.py # create_job, validate_recipient, process_job
│       └── pdf_service.py # render_certificate(...)
├── scripts/
│   └── make_template.py   # generates the placeholder templates/certificate.pdf
├── templates/
│   └── certificate.pdf
├── storage/               # generated PDFs (git-ignored): storage/{job_id}/{cert_id}.pdf
├── tests/
│   ├── conftest.py
│   ├── test_smoke.py
│   ├── test_generation.py
│   ├── test_create_job.py
│   ├── test_validation.py
│   ├── test_job_status.py
│   ├── test_failure_isolation.py
│   └── test_retrieval.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## 5. Configuration

| Var | Default | Purpose |
|---|---|---|
| `API_KEY` | `dev-secret-key` | Expected `X-API-Key` header value |
| `DATABASE_URL` | `sqlite:///./app.db` | SQLAlchemy URL |
| `STORAGE_DIR` | `./storage` | Where generated PDFs are written |
| `MAX_RECIPIENTS_PER_REQUEST` | `1000` | Upper bound per request |

## 6. Data Model

### `jobs`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID string, PK | The correlation ID returned to the client |
| `event_name` | string | Printed on every certificate |
| `status` | enum | `pending`, `processing`, `completed`, `completed_with_errors`, `failed` |
| `total` | int | Recipients in the request |
| `succeeded` | int | Default 0 |
| `failed` | int | Default 0 |
| `created_at` | datetime (UTC) | |
| `completed_at` | datetime, nullable | Set when processing ends |

### `certificates`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID string, PK | |
| `job_id` | FK → jobs.id, indexed | |
| `recipient_name` | string | May be blank (invalid rows are still stored) |
| `email` | string, nullable | |
| `course` | string, nullable | |
| `issue_date` | string, nullable | Raw value as sent; parsed during row validation |
| `status` | enum | `pending`, `processing`, `success`, `failed` |
| `file_path` | string, nullable | Set on success |
| `error_message` | string, nullable | Set on failure |
| `created_at` / `updated_at` | datetime | |

Final job status once processing ends:
- all certificates `success` → `completed`
- some `success`, some `failed` → `completed_with_errors`
- all `failed` → `failed`

## 7. API Contract

All endpoints are under `/v1`, require header `X-API-Key` (except `/health`), and return JSON except downloads. Errors are `{ "detail": "..." }`.

### 7.1 `POST /v1/jobs` → 202

Request:

```json
{
  "event_name": "PyCon Workshop 2026",
  "recipients": [
    { "name": "Asha Rao", "email": "asha@example.com", "course": "FastAPI 101", "date": "2026-10-01" }
  ]
}
```

Response: `{ "job_id": "uuid", "status": "pending", "total": 1 }`

Behaviour: check API key (401) → validate structure with Pydantic (422, no job created) → in ONE transaction insert the Job and one Certificate row per recipient (`pending`) → register `process_job(job_id)` with `BackgroundTasks` → return 202 immediately. Never generate PDFs inside the request.

### 7.2 `GET /v1/jobs/{job_id}` → 200

```json
{
  "job_id": "uuid",
  "event_name": "PyCon Workshop 2026",
  "status": "completed_with_errors",
  "total": 3, "succeeded": 2, "failed": 1, "pending": 0,
  "created_at": "...", "completed_at": "...",
  "certificates": [
    { "id": "uuid", "recipient_name": "Asha Rao", "status": "success", "error_message": null,
      "download_url": "/v1/jobs/{job_id}/certificates/{id}/download" },
    { "id": "uuid", "recipient_name": "", "status": "failed", "error_message": "name must not be blank",
      "download_url": null }
  ]
}
```

`pending` = total − succeeded − failed. `certificates` is paginated: `?page=1&page_size=100` (defaults 1 and 100, max page_size 500). Unknown job → 404.

### 7.3 `GET /v1/jobs/{job_id}/certificates/{cert_id}/download`

200 `application/pdf` with `Content-Disposition: attachment`. 404 if job or certificate unknown or the certificate does not belong to the job. 409 if the certificate is not `success` (message says pending or failed, and includes the error if failed).

### 7.4 `GET /v1/jobs/{job_id}/download`

200 `application/zip` containing every successful PDF, named `{sanitised_recipient_name}_{cert_id_first_8}.pdf`. 404 unknown job. 409 if the job is `pending` or `processing`, or finished with zero successes (clear message).

## 8. Validation Rules (two levels)

**Level 1: request structure. Whole request fails with 422, no job is created:**
- `event_name`: required string, 1–200 chars after trim.
- `recipients`: required list, 1 to `MAX_RECIPIENTS_PER_REQUEST` items.
- Each recipient must be an object; unknown fields ignored.
- Field *types* must be right (a recipient field that is a number or list instead of a string is a structure error).
- Level 1 must NOT reject bad *values* (blank name, bad email, bad date). Those pass through to Level 2.

**Level 2: recipient values. Only that row fails (`status=failed`, readable `error_message`), job continues:**
- `name`: required, non-blank after trim, max 100 chars.
- `email`: optional; valid email format if provided.
- `course`: optional; max 150 chars.
- `date`: optional; must parse as ISO `YYYY-MM-DD` if provided.

Implement Level 2 as `validate_recipient(cert) -> None` in `job_service.py`, raising `ValueError("human readable message")`.

## 9. Processing & PDF Design

### Processing choice: asynchronous background processing, client polls

Reasoning (must also go in the README):
- A bulk request may hold thousands of recipients; generating inside the HTTP request risks timeouts and blocks a worker.
- 202 + job ID keeps the API responsive; the client polls `GET /v1/jobs/{id}`.
- `BackgroundTasks` needs zero extra infrastructure, which suits the scope.

Trade-offs (state honestly in the README):
- Work runs in-process; a server restart mid-job does not resume automatically.
- Mitigation: progress is committed after every certificate, and `process_job` only processes certificates still `pending`, so it is safe to re-run.
- Upgrade path: swap `BackgroundTasks` for Celery/RQ + Redis (or an orchestrator like Airflow at larger scale) without changing the API, because `process_job(job_id)` is a standalone function.

### `process_job(job_id)` algorithm

```
open its OWN db session (never reuse the request session)
job.status = processing; commit
for cert in certificates where job_id matches and status == pending, ordered by created_at:
    cert.status = processing
    try:
        validate_recipient(cert)
        out_path = STORAGE_DIR / job_id / f"{cert.id}.pdf"
        pdf_service.render_certificate(cert, job.event_name, out_path)
        cert.status = success; cert.file_path = str(out_path); job.succeeded += 1
    except Exception as exc:
        cert.status = failed; cert.error_message = short readable message; job.failed += 1
        log full traceback server-side with job_id and cert id
    commit after EACH certificate
set final job.status per section 6; job.completed_at = now; commit
wrap the whole loop in try/finally so the job is never left stuck in "processing"
```

### PDF generation

- `constants.py` holds `TEMPLATE_PATH` and a dict of fields (`name`, `event_name`, `course`, `date`) each with `x`, `y`, font name, font size, alignment.
- `pdf_service.render_certificate(cert, event_name, out_path)`:
  1. Draw an in-memory overlay with ReportLab, writing each non-empty field at its coordinates (name centred).
  2. Read `templates/certificate.pdf` with pypdf, merge the overlay onto page 1, write to `out_path` (create parent dirs).
  3. Shrink-to-fit or truncate very long names so text stays on the page.
- `scripts/make_template.py` generates a simple landscape A4 placeholder (border, "Certificate of Completion" heading, static labels). Coordinates in `constants.py` must match it.
- Standard Latin fonts only; note in the README that non-Latin names need a registered TTF.

### Error handling rules

- Never leak stack traces to clients; store a short message in `error_message`.
- Stored file paths stay inside `STORAGE_DIR`; paths use UUIDs only. Sanitise any user string used in a filename (ZIP entry names).

---

# CHECKPOINTS

## CP0: Setup & Foundation

**Goal:** a runnable, empty-but-wired application with DB, models, auth and a passing smoke test. No business logic yet.

**Tasks**
1. Create the folder structure from section 4 (empty modules are fine where later checkpoints fill them in).
2. `requirements.txt`: fastapi, uvicorn[standard], sqlalchemy, pydantic, pydantic[email] (or email-validator), reportlab, pypdf, pytest, httpx.
3. `config.py`: load the section 5 settings from env with defaults. `.env.example` lists them.
4. `db.py`: engine from `DATABASE_URL` (SQLite needs `check_same_thread=False`), `SessionLocal`, `Base`, `get_db` dependency.
5. `models.py`: `Job` and `Certificate` exactly as in section 6, with enums for statuses.
6. `main.py`: create the FastAPI app, create tables on startup, `GET /health` returning `{"status": "ok"}` (no auth).
7. `auth.py`: dependency that reads `X-API-Key` and raises 401 `{ "detail": "Invalid or missing API key" }` on mismatch. Wire it onto the `/v1` router (an empty `routers/jobs.py` with the router and prefix is enough for now).
8. `.gitignore`: `__pycache__/`, `.venv/`, `*.db`, `.env`, `storage/`, `.pytest_cache/`.
9. `tests/conftest.py`: fixtures for a temp SQLite DB, a temp `STORAGE_DIR`, `get_db` override, a `client` fixture, and an `auth_headers` fixture.
10. `tests/test_smoke.py`: `/health` returns 200; a `/v1/...` route without a key returns 401; tables exist.

**Run**
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload      # confirm it boots and /docs loads, then stop it
pytest -v
```

**Done when**
- [ ] App boots and `/health` responds.
- [ ] Tables are created automatically on startup.
- [ ] Auth dependency rejects missing and wrong keys.
- [ ] `pytest` passes (smoke tests only).

**STOP and report.**

---

## CP1: PDF Engine

**Goal:** given a recipient, produce a correct certificate PDF from the template. No API involvement.

**Tasks**
1. `scripts/make_template.py`: generate `templates/certificate.pdf` (landscape A4 placeholder). Run it and commit the generated PDF.
2. `constants.py`: `TEMPLATE_PATH` and the field coordinate map that matches the placeholder.
3. `services/pdf_service.py`: implement `render_certificate(cert, event_name, out_path)` as described in section 9, including long-name shrink/truncate.
4. `tests/test_generation.py`:
   - output file exists and starts with `%PDF`;
   - it opens with pypdf, has exactly 1 page;
   - extracted text contains the recipient name and event name;
   - missing optional fields (no course, no date) still render;
   - a very long name does not raise and stays on the page;
   - parent directories are created automatically.
   Use a lightweight stand-in object or an unsaved `Certificate` instance; no DB needed.

**Run**
```
python scripts/make_template.py
pytest tests/test_generation.py -v
```
Also render one sample PDF to `storage/_sample.pdf` and tell the user to open it and confirm the layout looks right.

**Done when**
- [ ] Template exists and is committed.
- [ ] `render_certificate` produces valid, correctly laid-out PDFs.
- [ ] Generation tests pass.

**STOP and report.**

---

## CP2: Create Job & Validation

**Goal:** `POST /v1/jobs` validates the structure, persists the job and its certificate rows, and returns 202. Processing itself is a stub until CP3.

**Tasks**
1. `schemas.py`: `RecipientIn`, `JobCreateRequest` (Level 1 rules from section 8), `JobCreateResponse`. Recipient string fields must accept any string value (including blank/invalid) so bad values reach Level 2, but reject wrong types.
2. `job_service.create_job(db, request) -> Job`: single transaction; Job `pending`, `total=len(recipients)`, one `pending` Certificate per recipient.
3. `job_service.validate_recipient(cert)`: implement the Level 2 rules from section 8 (raising `ValueError` with readable messages). It is not called by the API yet.
4. `routers/jobs.py`: `POST /v1/jobs` returning 202. Register a placeholder `process_job(job_id)` in `BackgroundTasks` (a no-op function in `job_service.py` for now, replaced in CP3).
5. Tests:
   - `test_create_job.py`: valid request → 202 with `job_id`, status `pending`, correct `total`; DB has the job and the right number of certificate rows; wrong or missing API key → 401.
   - `test_validation.py` (Level 1): empty `recipients` → 422; missing `event_name` → 422; blank `event_name` → 422; more than the max recipients → 422; wrong field types → 422; and in every 422 case no job rows were created.
   - `test_validation.py` (Level 2 unit tests calling `validate_recipient` directly): blank name, over-long name, bad email, bad date each raise `ValueError` with a sensible message; a fully valid recipient and one with only a name both pass.
   - A request that contains a blank-name recipient plus valid ones is still accepted with 202 (row-level problems do not reject the request).

**Run**
```
pytest -v
```

**Done when**
- [ ] 202 returned fast with a usable `job_id`; rows persisted atomically.
- [ ] Structural errors → 422 with no side effects.
- [ ] Row-level rules implemented and unit-tested.
- [ ] All tests so far pass.

**STOP and report.**

---

## CP3: Processing, Status & Failure Isolation

**Goal:** jobs actually run in the background; clients can poll progress; one bad certificate never blocks the rest.

**Tasks**
1. `job_service.process_job(job_id)`: implement exactly the algorithm in section 9 (own DB session, per-certificate commit, try/except per certificate, final status derivation, try/finally safety net). It must be re-runnable: only `pending` certificates are processed.
2. Replace the CP2 no-op registration so `POST /v1/jobs` triggers the real `process_job`.
3. `GET /v1/jobs/{job_id}` per section 7.2, including `pending` count, per-certificate detail, `download_url` only for `success` rows, and pagination (`page`, `page_size`, max 500). Unknown job → 404.
4. Add the response schemas to `schemas.py`.
5. Tests:
   - `test_job_status.py`: all-valid job → `completed` with correct counters; mixed job → `completed_with_errors`; all-invalid job → `failed`; `pending` count is correct before/after processing (call `process_job` directly with a session to test mid-states if needed); pagination returns the right slices; unknown job → 404; auth required.
   - `test_failure_isolation.py`: monkeypatch `pdf_service.render_certificate` to raise for ONE specific recipient; assert that certificate is `failed` with an `error_message`, all others are `success` with files on disk, and the job is `completed_with_errors`. Add a case where a blank-name row (Level 2 failure) coexists with valid rows. Add a re-run case: running `process_job` again does not regenerate successful certificates or double-count.
   - Extend `test_generation.py`/`test_create_job.py` with one end-to-end test: POST a job, then read the DB or GET status and confirm files exist for the successes.

**Run**
```
pytest -v
```
Also start the server and run one manual `curl` POST + GET with 5 recipients (one invalid) to confirm the flow end to end. Show the output in the report.

**Done when**
- [ ] Background processing produces PDFs and correct statuses.
- [ ] Status endpoint reports counters, per-certificate state and reasons.
- [ ] A single failure (exception or validation) never stops other certificates.
- [ ] Job never stays stuck in `processing`.
- [ ] All tests pass.

**STOP and report.**

---

## CP4: Retrieval, README & Final Polish

**Goal:** clients can download certificates; project is documented and fully verified against the brief.

**Tasks**
1. Single download endpoint per section 7.3 (`FileResponse`, `application/pdf`, attachment header, 404 and 409 rules).
2. ZIP download endpoint per section 7.4. Build the ZIP in memory or a temp file; sanitise entry names; include only `success` certificates; handle 404 and 409 cases.
3. Tests in `test_retrieval.py`:
   - single PDF download → 200, `application/pdf`, body starts with `%PDF`;
   - downloading a `failed` or `pending` certificate → 409 with an explanatory message;
   - cert from a different job, or unknown cert/job → 404;
   - ZIP → 200, `application/zip`, contains exactly the successful PDFs and none of the failed ones, filenames sanitised (include a recipient named like `../evil/name`);
   - ZIP on an unfinished job or a job with zero successes → 409.
4. `README.md` containing, in this order:
   1. Overview and features
   2. Setup (Python version, venv, install, `.env` from `.env.example`, generating the template if missing)
   3. Run (`uvicorn app.main:app --reload`, `/docs`)
   4. Tests (`pytest -v`)
   5. Submit a request (`curl` with `X-API-Key` and a sample payload)
   6. Check status (`curl` plus sample response)
   7. Retrieve certificates (`curl -o` for a single PDF and for the ZIP)
   8. Design decisions: background processing choice and trade-offs (section 9), one PDF per recipient, two-level validation, template on disk with coordinates in `constants.py`, per-certificate commits, status derivation, how it would scale (Celery/RQ + Redis, or Airflow)
   9. Known limitations: in-process work not resumed after restart, single template, Latin fonts only
5. Final review pass:
   - run the full test suite;
   - verify every item in the acceptance checklist below by actually exercising it;
   - remove dead code and unused imports, and confirm no secrets are committed.

**Run**
```
pytest -v
```
Then follow the README from a clean clone mentally (or in a fresh venv) and confirm every command works as written.

**Done when**
- [ ] Single and ZIP downloads behave per the contract, including error cases.
- [ ] README commands all work as written.
- [ ] Full test suite passes.
- [ ] Final acceptance checklist is fully ticked.

**STOP and give a final summary, including a short file-by-file explanation the user can use to prepare for the interview.**

---

## Final Acceptance Checklist

- [ ] One POST creates a job for many recipients and returns 202 quickly.
- [ ] Bad recipient rows fail individually with clear messages; valid rows still generate.
- [ ] Job status shows totals, succeeded, failed, pending and per-certificate detail.
- [ ] Single PDF and ZIP downloads work; not-ready and failed cases return 409.
- [ ] State persists in the relational DB and files persist on disk across restarts.
- [ ] Tests cover: job creation, validation, generation, status/progress, individual failure, retrieval.
- [ ] README lets a stranger set up, run, test and use the API without help.
- [ ] Code is small and readable enough to explain function by function.

## Non-Goals (do not build)

Template editor or multiple templates, user accounts or JWT, webhooks, Airflow/Celery as the default, cloud storage, email delivery of certificates, frontend UI, rate limiting. Mention them in the README as future work only if useful.
