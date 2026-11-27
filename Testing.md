# Testing

## Current automated checks

Run from the repository root in the active virtual environment:

```powershell
python manage.py check
python -m pytest
```

The current focused tests cover role and theme choices/constraints, default profile values, the authenticated theme preference endpoint, session/cookie settings, PostgreSQL role/TLS configuration, and Argon2 as the preferred password hasher. The Django system check has passed. These checks do not require a live PostgreSQL server; database-backed behavior still needs PostgreSQL validation.

The local PostgreSQL connection timed out during this work, so the migration table, applied migration state, actual constraints, and database grants were not inspected. The user-role and theme constraint migrations have not been applied.

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

## Planned test coverage

As examination features are implemented, add tests for server-side role isolation, schedule boundaries, fixed attempt deadlines, answer autosave and resume, duplicate submission, objective scoring, manual grading limits, publication visibility, report authorization, and import validation.
