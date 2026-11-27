# Testing

## Current automated checks

Run from the repository root in the active virtual environment:

```powershell
python manage.py check
python -m pytest
```

The test suite covers account and role rules, exam creation/enrollment/attempt lifecycles, server-side authorization, snapshots, answer autosave, scoring and result publication, account import, profile/theme behavior, Turnstile verification, and manifest assets. Database-backed integration tests require PostgreSQL. The application role is intentionally not granted `CREATEDB`; use a separate test role/database with appropriate permissions rather than running tests against the live application database.

The full suite has passed against an isolated PostgreSQL 17 test cluster. The live application database is separate; verify its migration state and grants independently before deployment.

## Before a database-backed run

Configure PostgreSQL and `.env` with a dedicated `webthon_app` login, then run:

```powershell
python manage.py makemigrations --check
python manage.py migrate
python manage.py check --deploy
python -m pytest
```

Do not apply migrations against a database containing data you need to preserve without first reviewing the migration plan and making a backup.

## Manual UI smoke checks

- Open `/` at phone, tablet, and desktop widths; verify there is no horizontal overflow.
- Navigate between page sections using desktop links and the mobile bottom navigation.
- Confirm generated styles are served from `static/css/app.css` and do not request external CSS or fonts.
- Switch among all six theme swatches; use arrow keys in the radio group and verify the selected marker and page colors update.
- Use the sun/moon switch to toggle Plum and back; reload and verify the last theme appears before styles paint.
- While authenticated, change themes and reload; verify the profile preference persists and the browser network panel shows only local HTMX/Alpine/font assets.
- Use keyboard navigation and the skip link; confirm focus remains visible.
- Open `/accounts/login/`; verify username/password labels, CSRF token, and error feedback.
- Submit invalid credentials and verify the generic error does not disclose whether a username exists.
- Authenticate with a valid user and verify sign-out is a CSRF-protected POST.
- Check the browser network panel: page artwork is served from local static files.

## Remaining test coverage

Add tests for written-response grading, marking-rule edge cases, announcements/incidents, sandbox isolation through the UI, question imports, analytics, PDF/report verification authorization, workspace preferences, scratchpad persistence, and failure/load behavior for active attempts.
