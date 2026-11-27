# Testing

## Current automated checks

Run from the repository root in the active virtual environment:

```powershell
python manage.py check
python -m pytest
```

The current focused tests cover the user-role choices, candidate default role, core session/cookie settings, and Argon2 as the preferred password hasher. The Django system check has passed. These checks do not require a live PostgreSQL server; database-backed behavior still needs PostgreSQL validation.

## Before a database-backed run

Configure PostgreSQL and `.env`, then run:

```powershell
python manage.py makemigrations --check
python manage.py migrate
python manage.py check --deploy
python -m pytest
```

Do not apply migrations against a database containing data you need to preserve without first reviewing the migration plan and making a backup.

## Manual UI smoke checks

- Open `/` at phone, tablet, and desktop widths; verify there is no horizontal overflow.
- Navigate between page sections using the desktop links and the mobile disclosure menu.
- Use keyboard navigation and the skip link; confirm focus remains visible.
- Open `/accounts/login/`; verify username/password labels, CSRF token, and error feedback.
- Submit invalid credentials and verify the generic error does not disclose whether a username exists.
- Authenticate with a valid user and verify sign-out is a CSRF-protected POST.
- Check the browser network panel: page artwork is served from local static files.

## Planned test coverage

As examination features are implemented, add tests for server-side role isolation, schedule boundaries, fixed attempt deadlines, answer autosave and resume, duplicate submission, objective scoring, manual grading limits, publication visibility, report authorization, and import validation.
