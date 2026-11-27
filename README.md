# Web-e-Thon Online Examination System

The application uses Django 5, PostgreSQL, Django templates, and session-based authentication. The initial foundation defines the custom user model and its administrator, examiner, and candidate roles before any database migrations are created. Python 3.15 is being used locally at your direction; the project target remains Python 3.12.

The public landing page and sign-in screen are responsive, with screen adjustments in `static/css/responsive.css`, local SVG artwork, and a six-theme appearance picker. Authenticated theme choices are saved to the user's profile; anonymous choices are stored locally in the browser. Examiner workflows support exam settings, questions, enrollment, monitoring, and result publication. Candidate workflows support assigned exams, server-enforced attempt limits, resume, timed answering, offline answer queuing, submission, and published attempt history. PDF reports, scratchpad, manual grading, and deployment remain future work.

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

6. Either create demo accounts with a strong password provided through the current PowerShell session, or create a personal administrator:

   ```powershell
   $env:DEMO_PASSWORD = "use-a-strong-local-only-password"
   python manage.py seed_demo
   ```

   Or:

   ```powershell
   python manage.py createsuperuser
   ```

7. Start Django:

   ```powershell
   python manage.py runserver
   ```

The demo command creates local accounts for all three roles, does not overwrite existing demo accounts, and refuses to run when `DEBUG` is false. Demo usernames are `demo-admin`, `demo-examiner`, and `demo-candidate`; no demo password is committed to the repository.

Open `http://127.0.0.1:8000/` for the landing page. Sign-in is at `/accounts/login/`; Django administration is at `/admin/`.

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

Alpine.js 3.17.5 and HTMX 2.0.8 are self-hosted under `static/js/vendor/`; DM Serif Display is self-hosted under `static/fonts/` with its SIL Open Font License. No CDN is used at runtime.

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
