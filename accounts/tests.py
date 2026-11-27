import pytest
from django.conf import settings
from django.contrib.auth.hashers import identify_hasher, make_password
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, override_settings

from .models import User


def test_user_roles_are_defined():
    assert {value for value, _label in User.Role.choices} == {
        "admin",
        "examiner",
        "candidate",
    }


def test_new_user_defaults_to_candidate():
    assert User(username="sample").role == User.Role.CANDIDATE


def test_authentication_security_settings():
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert settings.SESSION_ENGINE == "django.contrib.sessions.backends.db"
    assert settings.SESSION_COOKIE_HTTPONLY
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"
    assert settings.CSRF_COOKIE_HTTPONLY
    assert settings.CSRF_COOKIE_SAMESITE == "Lax"


def test_database_uses_app_role_tls_setting_and_role_constraint():
    database = settings.DATABASES["default"]
    assert database["USER"].lower() != "postgres"
    assert database["OPTIONS"]["sslmode"] in {
        "disable",
        "allow",
        "prefer",
        "require",
        "verify-ca",
        "verify-full",
    }
    assert any(
        constraint.name == "accounts_user_valid_role"
        for constraint in User._meta.constraints
    )


def test_argon2_is_the_default_password_hasher():
    assert identify_hasher(make_password("test-password")).algorithm == "argon2"


def test_public_homepage_and_login_page_render():
    client = Client()

    home = client.get("/")
    login = client.get("/accounts/login/")

    assert home.status_code == 200
    assert b'data-theme="ivory"' in home.content
    assert b"/static/css/app.css" in home.content
    assert b'id="platform"' in home.content
    assert b'id="how-it-works"' in home.content
    assert b'class="mobile-bottom-nav"' in home.content
    assert login.status_code == 200
    assert b'name="csrfmiddlewaretoken"' in login.content


@override_settings(DEBUG=False)
def test_demo_seed_command_refuses_non_debug_settings():
    with pytest.raises(CommandError, match="DEBUG=true"):
        call_command("seed_demo")


@override_settings(DEBUG=True)
def test_demo_seed_command_requires_a_password(monkeypatch):
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)

    with pytest.raises(CommandError, match="DEMO_PASSWORD"):
        call_command("seed_demo")
