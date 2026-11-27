# Web-e-Thon Online Examination System

The application uses Django 5, PostgreSQL, Django templates, and session-based authentication. The initial foundation defines the custom user model and its administrator, examiner, and candidate roles before any database migrations are created. Python 3.15 is being used locally at your direction; the project target remains Python 3.12.

## Local setup (Windows PowerShell)

1. Install PostgreSQL and create a local database and user.
2. Create and activate a virtual environment:

   ```powershell
   py -3.15 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install project dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env`, generate a unique key with `python -c "import secrets; print(secrets.token_urlsafe(50))"`, then set it and your local PostgreSQL credentials in `.env`.
5. Apply migrations after confirming `accounts.User` is configured as `AUTH_USER_MODEL`:

   ```powershell
   python manage.py migrate
   ```

6. Create an administrator and start Django:

   ```powershell
   python manage.py createsuperuser
   python manage.py runserver
   ```

The `.env` file is local-only and ignored by Git. `COOKIE_SECURE=false` is for local HTTP development; set it to `true` behind HTTPS in deployment.

## Tests

Run the test suite with:

```powershell
pytest
```
