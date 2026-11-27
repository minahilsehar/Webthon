import json
from io import BytesIO
from urllib.error import URLError
from urllib.parse import parse_qs
from unittest.mock import patch

import pytest
from django.conf import settings
from django.test import Client, override_settings

from apps.accounts.forms.turnstile import (
    TURNSTILE_VERIFY_URL,
    TurnstileAuthenticationForm,
    TurnstileUnavailable,
    verify_turnstile_response,
)


@override_settings(
    DEBUG=True,
    TURNSTILE_ENABLED=True,
    TURNSTILE_SITE_KEY="test-site-key",
    TURNSTILE_SECRET_KEY="test-secret-key",
    TURNSTILE_TEST_MODE=True,
)
def test_login_page_renders_turnstile_widget_and_robot_icon():
    response = Client().get("/accounts/login/")

    assert response.status_code == 200
    assert b'data-sitekey="test-site-key"' in response.content
    assert b'class="cf-turnstile"' in response.content
    assert b"challenges.cloudflare.com/turnstile/v0/api.js" in response.content
    assert b"images/captcha-robot.png" in response.content
    assert b"not production bot protection" in response.content


@override_settings(
    DEBUG=True,
    TURNSTILE_ENABLED=True,
    TURNSTILE_SITE_KEY="test-site-key",
    TURNSTILE_SECRET_KEY="test-secret-key",
    TURNSTILE_TEST_MODE=True,
)
def test_login_rejects_missing_token_before_authentication():
    form = TurnstileAuthenticationForm(
        data={"username": "candidate", "password": "valid-password"}
    )

    with (
        patch("apps.accounts.forms.turnstile.verify_turnstile_response") as verify,
        patch("django.contrib.auth.forms.authenticate") as authenticate,
    ):
        assert not form.is_valid()

    assert "human verification" in str(form.errors).lower()
    verify.assert_not_called()
    authenticate.assert_not_called()


@override_settings(
    DEBUG=True,
    TURNSTILE_ENABLED=True,
    TURNSTILE_SITE_KEY="test-site-key",
    TURNSTILE_SECRET_KEY="test-secret-key",
    TURNSTILE_TEST_MODE=True,
)
def test_login_rejects_a_token_cloudflare_does_not_verify(monkeypatch):
    monkeypatch.setattr(
        "apps.accounts.forms.turnstile.verify_turnstile_response",
        lambda token, secret: False,
    )
    form = TurnstileAuthenticationForm(
        data={
            "username": "candidate",
            "password": "valid-password",
            "cf-turnstile-response": "invalid-response",
        }
    )

    assert not form.is_valid()
    assert "could not be verified" in str(form.errors).lower()


def test_turnstile_verification_posts_token_and_secret():
    response = BytesIO(b'{"success": true}')

    with patch("apps.accounts.forms.turnstile.urlopen", return_value=response) as urlopen:
        assert verify_turnstile_response("response-token", "private-test-secret")

    request, = urlopen.call_args.args
    assert request.full_url == TURNSTILE_VERIFY_URL
    assert parse_qs(request.data.decode("ascii")) == {
        "response": ["response-token"],
        "secret": ["private-test-secret"],
    }
    assert urlopen.call_args.kwargs["timeout"] == 5


def test_turnstile_verification_fails_closed_when_provider_is_unavailable():
    with (
        patch(
            "apps.accounts.forms.turnstile.urlopen",
            side_effect=URLError("offline"),
        ),
        pytest.raises(TurnstileUnavailable),
    ):
        verify_turnstile_response("response-token", "private-test-secret")


def test_web_manifest_declares_install_icons_and_shortcuts():
    manifest_path = settings.BASE_DIR / "static" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["short_name"] == "Imtihanify"
    assert manifest["name"].startswith("Imtihanify")
    assert manifest["display"] == "standalone"
    assert {icon["sizes"] for icon in manifest["icons"]} == {"192x192", "512x512"}
    assert {shortcut["url"] for shortcut in manifest["shortcuts"]} == {
        "/accounts/login/",
        "/exams/",
        "/exams/manage/",
    }
