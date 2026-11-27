import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "").strip()
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "").strip()
TURNSTILE_TEST_MODE = os.environ.get("TURNSTILE_TEST_MODE", "false").lower() == "true"
TURNSTILE_ENABLED = bool(TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY)
TURNSTILE_TEST_SITE_KEYS = {
    "1x00000000000000000000AA",
    "2x00000000000000000000AB",
    "1x00000000000000000000BB",
    "2x00000000000000000000BB",
    "3x00000000000000000000FF",
}
TURNSTILE_TEST_SECRET_KEYS = {
    "1x0000000000000000000000000000000AA",
    "2x0000000000000000000000000000000AA",
    "3x0000000000000000000000000000000AA",
}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
DB_USER = os.environ.get("DB_USER", "webthon_app")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_SSLMODE = os.environ.get("DB_SSLMODE", "disable" if DEBUG else "require").lower()

if bool(TURNSTILE_SITE_KEY) != bool(TURNSTILE_SECRET_KEY):
    raise ImproperlyConfigured(
        "Set both TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY."
    )
if TURNSTILE_TEST_MODE and not DEBUG:
    raise ImproperlyConfigured("TURNSTILE_TEST_MODE is only allowed with DEBUG=true.")
if not DEBUG and not TURNSTILE_ENABLED:
    raise ImproperlyConfigured(
        "Set live TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY for non-debug environments."
    )
if not DEBUG and (
    TURNSTILE_SITE_KEY in TURNSTILE_TEST_SITE_KEYS
    or TURNSTILE_SECRET_KEY in TURNSTILE_TEST_SECRET_KEYS
):
    raise ImproperlyConfigured(
        "Cloudflare Turnstile test keys cannot be used in non-debug environments."
    )

if not DEBUG:
    if not DB_USER:
        raise ImproperlyConfigured("Set DB_USER for non-debug environments.")
    if not DB_PASSWORD:
        raise ImproperlyConfigured("Set DB_PASSWORD for non-debug environments.")
    if DB_USER.lower() == "postgres":
        raise ImproperlyConfigured("Use a dedicated non-superuser DB_USER, not postgres.")
    if DB_SSLMODE not in {"require", "verify-ca", "verify-full"}:
        raise ImproperlyConfigured(
            "Non-debug database connections must use DB_SSLMODE=require or stronger."
        )

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "apps.accounts",
    "apps.exams",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "axes.middleware.AxesMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    try:
        database_url = urlsplit(DATABASE_URL)
        database_name = unquote(database_url.path.lstrip("/"))
        database_user = unquote(database_url.username or "")
        database_password = unquote(database_url.password or "")
        database_host = database_url.hostname
        database_port = database_url.port or 5432
    except ValueError as error:
        raise ImproperlyConfigured(
            "DATABASE_URL must be a valid PostgreSQL connection URL."
        ) from error

    if database_url.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured(
            "DATABASE_URL must use the postgres or postgresql scheme."
        )
    if not all((database_name, database_user, database_password, database_host)):
        raise ImproperlyConfigured(
            "DATABASE_URL must include a database, username, password, and host."
        )

    database_options = {
        key: values[-1]
        for key, values in parse_qs(database_url.query).items()
    }
    database_options.setdefault("sslmode", DB_SSLMODE)
    DB_USER = database_user
    DB_PASSWORD = database_password
    DB_HOST = database_host
    DB_PORT = str(database_port)
    DB_SSLMODE = database_options["sslmode"].lower()
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": database_name,
            "USER": DB_USER,
            "PASSWORD": DB_PASSWORD,
            "HOST": DB_HOST,
            "PORT": DB_PORT,
            "OPTIONS": database_options,
            "CONN_MAX_AGE": 0,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "webthon"),
            "USER": DB_USER,
            "PASSWORD": DB_PASSWORD,
            "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
            "PORT": os.environ.get("DB_PORT", "5432"),
            "OPTIONS": {"sslmode": DB_SSLMODE},
        }
    }

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = COOKIE_SECURE
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = COOKIE_SECURE
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"
