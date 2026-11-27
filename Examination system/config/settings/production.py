import os
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403


DEBUG = False


def _environment_values(name):
    return [
        value.strip()
        for value in os.environ.get(name, "").split(",")
        if value.strip()
    ]


def _vercel_host(name):
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    parsed = urlsplit(value if "://" in value else f"https://{value}")
    return parsed.hostname


if not DATABASE_URL:  # noqa: F405
    raise ImproperlyConfigured("Set DATABASE_URL to the Neon PostgreSQL URL.")

if not DB_USER or DB_USER.lower() == "postgres":  # noqa: F405
    raise ImproperlyConfigured(
        "Set DATABASE_URL to a dedicated non-superuser database account."
    )
if not DB_PASSWORD:  # noqa: F405
    raise ImproperlyConfigured("DATABASE_URL must include a database password.")
if DB_SSLMODE not in {"require", "verify-ca", "verify-full"}:  # noqa: F405
    raise ImproperlyConfigured(
        "Production database connections must use SSL mode require or stronger."
    )

if not TURNSTILE_ENABLED:  # noqa: F405
    raise ImproperlyConfigured(
        "Set live TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY values."
    )
if TURNSTILE_TEST_MODE or (  # noqa: F405
    TURNSTILE_SITE_KEY in TURNSTILE_TEST_SITE_KEYS  # noqa: F405
    or TURNSTILE_SECRET_KEY in TURNSTILE_TEST_SECRET_KEYS  # noqa: F405
):
    raise ImproperlyConfigured("Cloudflare Turnstile test keys are not allowed.")

vercel_hosts = [
    host
    for host in (
        _vercel_host("VERCEL_URL"),
        _vercel_host("VERCEL_PROJECT_PRODUCTION_URL"),
    )
    if host
]
ALLOWED_HOSTS = list(dict.fromkeys(vercel_hosts + _environment_values("ALLOWED_HOSTS")))
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must not contain a wildcard.")

vercel_origins = [f"https://{host}" for host in vercel_hosts]
CSRF_TRUSTED_ORIGINS = list(
    dict.fromkeys(vercel_origins + _environment_values("CSRF_TRUSTED_ORIGINS"))
)

STATIC_URL = "/static/"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 3600
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
