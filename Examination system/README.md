# Imtihanify — Online Examination System

## Architecture (MVC)

The Django project uses a clear MVC-style layout:

- `config/`: project settings and URL routing.
- `apps/accounts/`: account data and the seeded demo-user command; `models/`, `services/`, `controllers/`, `forms/`, `templates/`, and `tests/` separate the account layers.
- `apps/exams/`: examination data and attempt rules; `models/`, `services/`, `controllers/`, `forms/`, `templates/`, and `tests/` separate the exam layers.
- `templates/`: shared layouts and presentation partials.
- `static/`: CSS, JavaScript, fonts, and images.

Django maps controllers to request-handling modules, models plus services to application data and business rules, and templates/static assets to the view layer.

The application uses Django 5, PostgreSQL, Django templates, and session-based authentication. The initial foundation defines the custom user model and its administrator, examiner, and candidate roles before any database migrations are created. Python 3.15 is being used locally at your direction; the project target remains Python 3.12.

The public landing page and sign-in screen are responsive, with local artwork and a six-theme appearance picker. Examiner workflows support exam settings, objective-choice questions, candidate enrollment, basic attempt monitoring, and result publication. Candidate workflows support assigned exams, server-enforced attempt limits and deadlines, resume, answer snapshots, autosave, an IndexedDB offline queue, submission, and published attempt history.

This is not yet a complete implementation of the Web-e-Thon problem statement. Missing or partial items include a reusable question bank with categories/difficulty and randomization; written responses and manual grading; candidate question navigation and review flags; exam announcements and incident history; PDF and verifiable reports; a candidate-facing sandbox; question import; question analytics; exam-workspace customization; a digital scratchpad; production deployment; and realistic load testing.

## Local setup (Windows PowerShell)

1. Install PostgreSQL and create a dedicated application role and database. Do not configure Django with the PostgreSQL `postgres` superuser:

   ```sql
   CREATE ROLE webthon_app LOGIN PASSWORD 'choose-a-unique-local-password';
   CREATE DATABASE webthon OWNER webthon_app;
   ```
2. Create and activate a virtual environment:

   ```powershell
   py -3.15 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install project dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env`, generate a unique key with `python -c "import secrets; print(secrets.token_urlsafe(50))"`, then set it and your local PostgreSQL credentials in `.env`. For non-debug environments, use a dedicated database role/password and set `DB_SSLMODE=require` or stronger; insecure SSL modes are rejected.
5. Apply the current database migrations after verifying the configured database:

   ```powershell
   python manage.py migrate
   ```

6. To seed judging data, explicitly enable demo mode in the current PowerShell session and run:

   ```powershell
   $env:DEMO_MODE = "true"
   python manage.py seed_demo
   ```

   This creates the judging accounts `admin` / `admin`, `examiner` / `examiner`, and `2026-demo-001` / `candidate` (plus two demo candidates), sample catalog entries, exams, questions, and enrollments. These known passwords are for judging only; change or disable these accounts after the event. The command does nothing unless `DEMO_MODE=true` is explicitly set. It may be run against the intended database by setting that database's environment variables first.

   Or create a personal administrator:

   ```powershell
   python manage.py createsuperuser
   ```

7. Start Django:

   ```powershell
   python manage.py runserver
   ```

Demo data is created through the same atomic account-creation service used by account creation in Django Admin. User identifiers are normalized to lowercase and unique without regard to case. Departments, degrees, and subjects are database-backed, can be managed separately in Django Admin, and cannot be deleted while assigned. Catalog changes and account creation are recorded in the account audit log.

Administrators can add one account in Django Admin or use **Import users from CSV** on the user list. CSV files require `username,password,role`; `email`, `first_name`, `last_name`, `department`, `degrees`, and `subjects` are optional. Separate multiple degrees or subjects with semicolons. Passwords must pass the configured Django validators. Each request is limited to 20 users and 512 KB; larger imports are rejected without truncation because this project does not configure a background worker. The import reports created, skipped, and failed rows with their CSV line numbers.

Open `http://127.0.0.1:8000/` for the landing page. Sign-in is at `/accounts/login/`; Django administration is at `/admin/`.

Cloudflare Turnstile is enabled on sign-in when both `TURNSTILE_SITE_KEY` and `TURNSTILE_SECRET_KEY` are configured. For local development, use Cloudflare's published test keys and set `TURNSTILE_TEST_MODE=true`; test keys do not provide production bot protection. Non-debug environments require a live key pair, and test mode is rejected.

The site includes a web app manifest, install icons, and shortcuts for sign-in, candidate exams, and the examiner workspace. On localhost or HTTPS, Chrome can install the site from its install icon or the browser menu; the installed app can then be pinned and its manifest shortcuts used.

Candidates use `/exams/` to view assigned exams. Examiners use `/exams/manage/` to create exams, assign candidates, configure attempt limits and scoring policies, monitor candidates, and publish results. Add at least one active question before publishing an exam. The candidate answer page stores unsent changes in browser IndexedDB and retries them on reconnect; submitted data is still validated and saved by Django.

The `.env` file is local-only and ignored by Git. `COOKIE_SECURE=false` and `DB_SSLMODE=disable` are for local development only. Non-debug settings require HTTPS database transport and a non-superuser database account.

## Frontend styles

The compiled stylesheet is committed at `static/css/app.css`; pages do not load CSS from a CDN. To rebuild it on Windows, download the pinned Tailwind standalone CLI into the ignored project-local `.tools` folder and verify its published SHA-256:

```powershell
New-Item -ItemType Directory -Force .tools | Out-Null
curl.exe --fail --location --output .tools\tailwindcss-windows-x64.exe https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.5/tailwindcss-windows-x64.exe
if ((Get-FileHash .tools\tailwindcss-windows-x64.exe -Algorithm SHA256).Hash.ToLowerInvariant() -ne "2803583268c53f4713e89943e211081fddb186c0a4a7d07b5c342c6ae853ec95") { throw "Tailwind CLI checksum mismatch." }
& .\.tools\tailwindcss-windows-x64.exe -i static\css\tailwind.input.css -o static\css\app.css
```

The standalone binary is local and ignored by Git; the generated CSS is the tracked runtime asset.

Alpine.js 3.17.5 and HTMX 2.0.8 are self-hosted under `static/js/vendor/`. The interface uses the system Times New Roman font stack. Cloudflare's Turnstile script is loaded only on sign-in when the CAPTCHA is configured.

## Tests

Run the test suite with:

```powershell
pytest
```

## Project documents

- [Product requirements](PRD.md)
- [Technical requirements](TRD.md)
- [Implementation plan](Implementation_Plan.md)
- [Testing guide](Testing.md)
- [Glossary](Glossary.md)

Deployment configuration is intentionally not included in this implementation step.
