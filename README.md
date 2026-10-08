  # Bulk Certificate Generator

  A high-performance backend API service built with FastAPI that accepts bulk certificate generation requests in a single call, generates individualized PDF certificates from a pre-defined template, tracks granular job- and certificate-level progress, and provides single or bulk (ZIP) file retrieval.

  ---

  ## 1. Overview and Features

  - **Bulk Submission**: Accept up to 1,000 recipients in a single HTTP request with immediate response (`202 Accepted`).
  - **Two-Level Validation**:
    - *Level 1 (Structural)*: Fails fast with `422 Unprocessable Entity` without touching the database if request structure, field types, or bounds are violated.
    - *Level 2 (Row-Level)*: Validates individual recipient data (name required/length, email syntax, course length, ISO date format); invalid rows fail gracefully without aborting peers.
  - **Resilient Background Processing**: PDF rendering runs asynchronously via FastAPI's `BackgroundTasks`, committing progress after each certificate.
  - **Failure Isolation**: A crash or validation issue on one certificate never halts the remaining batch.
  - **Dynamic Text Layout**: In-memory text overlay with automatic shrink-to-fit and truncation for long names, merged onto a landscape A4 vector template using ReportLab and pypdf.
  - **Progress Tracking & Pagination**: `GET /v1/jobs/{job_id}` exposes counters (`total`, `succeeded`, `failed`, `pending`) and paginated certificate records with download URLs.
  - **Flexible File Retrieval**: Download individual certificates (`application/pdf`) or a consolidated archive of all successful certificates (`application/zip`) with sanitized filenames.
  - **Zero Heavy Infrastructure**: Built with SQLite (configurable to PostgreSQL via environment) and zero external queues for lean, deterministic execution.

  ---

  ## 2. Setup

  ### Prerequisites
  - Python 3.10+ (Python 3.11+ recommended)
  - `pip` package manager

  ### Installation

  1. **Clone the repository and enter directory**:
    ```bash
    cd Bulk-pdf-generator
    ```

  2. **Create and activate a virtual environment**:
    - On Linux / macOS:
      ```bash
      python -m venv .venv
      source .venv/bin/activate
      ```
    - On Windows (PowerShell):
      ```powershell
      python -m venv .venv
      .\.venv\Scripts\Activate.ps1
      ```

  3. **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

  4. **Configure environment**:
    Copy `.env.example` to `.env`:
    ```bash
    cp .env.example .env
    ```
    *Default configuration:*
    - `API_KEY=dev-secret-key`
    - `DATABASE_URL=sqlite:///./app.db`
    - `STORAGE_DIR=./storage`
    - `MAX_RECIPIENTS_PER_REQUEST=1000`

  5. **Generate certificate base template** (if missing):
    ```bash
    python scripts/make_template.py
    ```
    This generates `templates/certificate.pdf`.

  ---

  ## 3. Run

  Start the FastAPI application with Uvicorn:

  ```bash
  uvicorn app.main:app --reload
  ```

  - **Base URL**: `http://127.0.0.1:8000`
  - **Health Check**: `http://127.0.0.1:8000/health`
  - **Interactive Swagger Documentation**: `http://127.0.0.1:8000/docs`
  - **ReDoc Documentation**: `http://127.0.0.1:8000/redoc`

  ---

  ## 4. Tests

  Run the comprehensive automated test suite with pytest:

  ```bash
  pytest -v
  ```

  The test suite covers:
  - Smoke tests & table creation (`test_smoke.py`)
  - Template & PDF overlay generation (`test_generation.py`)
  - Job creation & authentication (`test_create_job.py`)
  - Two-level structural & row-level validation (`test_validation.py`)
  - Job progress, status transitions & pagination (`test_job_status.py`)
  - Failure isolation & re-run idempotency (`test_failure_isolation.py`)
  - Individual PDF and bulk ZIP downloads (`test_retrieval.py`)

  ---

  ## 5. Submit a Request

  Submit a batch of recipients using `POST /v1/jobs` with the `X-API-Key` header:

  ```bash
  curl -X POST http://127.0.0.1:8000/v1/jobs \
    -H "X-API-Key: dev-secret-key" \
    -H "Content-Type: application/json" \
    -d '{
      "event_name": "PyCon Workshop 2026",
      "recipients": [
        {
          "name": "Asha Rao",
          "email": "asha@example.com",
          "course": "FastAPI 101",
          "date": "2026-10-01"
        },
        {
          "name": "Bob Smith",
          "email": "bob@example.com",
          "course": "Docker 101",
          "date": "2026-10-02"
        },
        {
          "name": "   ",
          "email": "invalid@example.com",
          "course": "Failing Row",
          "date": "2026-10-03"
        }
      ]
    }'
  ```

  **Response (HTTP 202 Accepted):**
  ```json
  {
    "job_id": "ca93b57a-ce68-4918-ac6f-9899f13b6c04",
    "status": "pending",
    "total": 3
  }
  ```

  ---

  ## 6. Check Status

  Poll the job status using `GET /v1/jobs/{job_id}`:

  ```bash
  curl http://127.0.0.1:8000/v1/jobs/ca93b57a-ce68-4918-ac6f-9899f13b6c04 \
    -H "X-API-Key: dev-secret-key"
  ```

  **Response (HTTP 200 OK):**
  ```json
  {
    "job_id": "ca93b57a-ce68-4918-ac6f-9899f13b6c04",
    "event_name": "PyCon Workshop 2026",
    "status": "completed_with_errors",
    "total": 3,
    "succeeded": 2,
    "failed": 1,
    "pending": 0,
    "created_at": "2026-10-08T16:48:32.660987",
    "completed_at": "2026-10-08T16:48:32.779524",
    "certificates": [
      {
        "id": "0d1ca912-be5c-4075-aed9-c1eac312e450",
        "recipient_name": "Asha Rao",
        "status": "success",
        "error_message": null,
        "download_url": "/v1/jobs/ca93b57a-ce68-4918-ac6f-9899f13b6c04/certificates/0d1ca912-be5c-4075-aed9-c1eac312e450/download"
      },
      {
        "id": "de0795cd-6755-4cbe-ba25-da511694b579",
        "recipient_name": "Bob Smith",
        "status": "success",
        "error_message": null,
        "download_url": "/v1/jobs/ca93b57a-ce68-4918-ac6f-9899f13b6c04/certificates/de0795cd-6755-4cbe-ba25-da511694b579/download"
      },
      {
        "id": "0a6e2d72-3022-423a-a0c3-3da964dd7916",
        "recipient_name": "   ",
        "status": "failed",
        "error_message": "Recipient name is required and must not be blank",
        "download_url": null
      }
    ]
  }
  ```

  *Pagination query parameters are supported:* `?page=1&page_size=100` (max `page_size` 500).

  ---

  ## 7. Retrieve Certificates

  ### Single Certificate Download
  Use the certificate's `download_url`:

  ```bash
  curl -o certificate.pdf \
    http://127.0.0.1:8000/v1/jobs/ca93b57a-ce68-4918-ac6f-9899f13b6c04/certificates/0d1ca912-be5c-4075-aed9-c1eac312e450/download \
    -H "X-API-Key: dev-secret-key"
  ```
  - Returns `200 application/pdf`.
  - If the certificate failed or is still pending, returns `409 Conflict` with the specific reason.

  ### Bulk ZIP Download
  Download all successful certificates in a single archive:

  ```bash
  curl -o certificates.zip \
    http://127.0.0.1:8000/v1/jobs/ca93b57a-ce68-4918-ac6f-9899f13b6c04/download \
    -H "X-API-Key: dev-secret-key"
  ```
  - Returns `200 application/zip` containing only successful certificates.
  - Filenames inside the archive follow `{sanitised_recipient_name}_{cert_id_first_8}.pdf`.
  - If the job is still pending/processing or finished with zero successes, returns `409 Conflict`.

  ---

  ## 8. Design Decisions

  ### Asynchronous Background Processing
  - **Why**: Generating hundreds or thousands of PDF documents inside a synchronous HTTP request causes client connection timeouts and locks HTTP worker threads. Returning `202 Accepted` with a `job_id` keeps the API fast and responsive. Clients poll `GET /v1/jobs/{job_id}` for status.
  - **Choice of `BackgroundTasks`**: FastAPI's built-in `BackgroundTasks` requires zero external infrastructure (no Redis, RabbitMQ, or Celery worker processes needed), minimizing operational complexity and dependencies for the service scope.
  - **Trade-offs**: Tasks execute in-process. If the server process restarts midway through a job, background tasks do not automatically resume.
  - **Mitigation & Re-run Safety**:
    - The database session is dedicated to the background task (never reusing the request session).
    - Progress is committed to the database after **each individual certificate**.
    - `process_job(job_id)` only selects certificates with status `pending`. Re-running `process_job` skips already generated certificates and does not duplicate counts.
  - **Scaling Path**: Because `process_job(job_id)` is a standalone, decoupled function that only requires the `job_id`, migrating to an external queue (such as Celery, RQ, or an orchestrator like Airflow) requires changing only the task dispatch line in `routers/jobs.py` without modifying the core API contract or PDF engine.

  ### One PDF Per Recipient
  - Generating individual PDFs per recipient guarantees true modularity: individual recipients can be downloaded immediately, regenerated independently, or distributed via separate channels.

  ### Two-Level Validation Strategy
  - **Level 1 (Structural)**: Evaluated at the HTTP boundary via Pydantic v2. Ensures required JSON shapes, list length boundaries (1 to `MAX_RECIPIENTS_PER_REQUEST`), and strict types. Rejections fail with `422` before any database records are created.
  - **Level 2 (Row-Level)**: Evaluated per recipient in the background processing worker. If one recipient has a blank name, an invalid email, or an invalid date, that row is marked `failed` with a clear explanation, while all other valid recipients are processed successfully.

  ### Template on Disk with Coordinate Configuration
  - A clean, vector-rendered base template (`templates/certificate.pdf`) is separated from the overlay logic.
  - Field coordinates, fonts, colors, and maximum bounds are centralized in `app/constants.py`. Changing layouts or branding requires zero alterations to the core PDF generation algorithm.

  ### Per-Certificate Commits & Final Status Derivation
  - Committing after each certificate ensures real-time client polling visibility and fault tolerance against mid-batch worker crashes.
  - Final job status is derived deterministically:
    - All succeeded $\rightarrow$ `completed`
    - Succeeded + Failed $\rightarrow$ `completed_with_errors`
    - All failed $\rightarrow$ `failed`

  ---

  ## 9. Known Limitations

  1. **In-Process Background Work**: Background execution relies on FastAPI's `BackgroundTasks`. An ungraceful server termination will interrupt in-flight jobs (mitigated by per-row DB commits and re-runnable idempotent processing).
  2. **Single Predefined Template**: The application merges onto a single predefined certificate template located at `templates/certificate.pdf`.
  3. **Latin Font Support**: Standard built-in PDF fonts (Helvetica) are used for high speed and minimal dependencies. Rendering non-Latin character sets (such as Arabic, Chinese, or Cyrillic) would require registering TrueType (`.ttf`) fonts in ReportLab.
