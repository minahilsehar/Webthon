# Technical Requirements Document

## Fixed stack

- Python 3.12 target; Python 3.15 is the current local development interpreter by explicit temporary choice.
- Django 5, PostgreSQL, Django templates, HTMX, Alpine.js, and Tailwind CSS.
- Chart.js for charts; ReportLab for PDF; `qrcode` for QR generation.
- Django built-in authentication with a custom `AbstractUser`, role field, Argon2 hashing, django-axes, database-backed sessions, and Django CSRF protection.
- pytest-django; Gunicorn and WhiteNoise for the selected free-host deployment approach.

Do not introduce a dependency outside this fixed stack without user approval. The current landing page uses local CSS and does not yet need charting or asynchronous interaction.

## Current architecture

- `config/`: project settings and URL routing.
- `accounts/`: custom user, role choices, Django admin integration, and initial migration.
- `exams/`: exam, enrollment, question snapshots, attempts, answers, and audit records; attempt start and attempt-policy services.
- `templates/`: shared site layout, public landing page, and built-in-auth login template.
- `static/`: Tailwind input/output, theme/component/responsive CSS sources, and local SVG artwork.
- Tailwind CSS is compiled offline by the pinned standalone CLI into a tracked stylesheet; runtime pages use no CDN assets.
- PostgreSQL settings are read from `.env`/environment variables.
- Django connects using a dedicated application role (never `postgres` in non-debug mode); non-debug database connections require SSL.
- Django sessions are database-backed. Password hashing prefers Argon2.

## Security requirements

- Use `AUTH_USER_MODEL = "accounts.User"` before the first migration.
- Keep secrets out of source control; configure `SECRET_KEY` outside code.
- Use a dedicated PostgreSQL login for the app and never grant it the PostgreSQL superuser role.
- Require encrypted PostgreSQL transport outside debug mode; use `verify-full` when the host and CA configuration permit certificate verification.
- Constrain role values in the database as well as through Django form/model choices.
- Use `SESSION_COOKIE_HTTPONLY`, `CSRF_COOKIE_HTTPONLY`, and SameSite=Lax.
- Secure session and CSRF cookies by default; disable Secure only for local HTTP development.
- Apply backend authorization to every protected examination, attempt, and result operation.
- Protect state-changing forms with CSRF tokens; do not use GET for state changes.
- Keep answer keys, unpublished results, and personal records out of public responses.

## Data integrity and reliability

- Treat server time as authoritative for scheduling and attempt deadlines.
- Make answer saves idempotent and submissions safe against duplicate requests.
- Snapshot assigned questions and marking rules for each attempt.
- Retain grading state and audit changes needed for review and disputes.
- Validate all data on the server, even when client-side validation is also used.

## Configuration and local operation

Use `.env.example` as the template for local settings. Never commit `.env`. PostgreSQL must be available before applying migrations or running database-dependent integration tests. Run `python manage.py check`, `python manage.py makemigrations --check`, and `pytest` before committing a change.

## Runtime compatibility

Python 3.15 is outside the stated Python 3.12 target. Re-run dependency installation, migrations, tests, and Django checks under Python 3.12 before treating the target runtime as validated.
