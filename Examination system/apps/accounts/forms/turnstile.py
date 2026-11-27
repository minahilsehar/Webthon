import json
import logging
from http.client import HTTPException
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class TurnstileUnavailable(Exception):
    pass


def verify_turnstile_response(token, secret):
    request = Request(
        TURNSTILE_VERIFY_URL,
        data=urlencode({"secret": secret, "response": token}).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read(16_384))
    except (
        HTTPException,
        OSError,
        TimeoutError,
        URLError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        logger.warning(
            "Cloudflare Turnstile verification failed (%s).",
            type(error).__name__,
        )
        raise TurnstileUnavailable from error

    return isinstance(result, dict) and result.get("success") is True


class TurnstileAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.turnstile_enabled = settings.TURNSTILE_ENABLED
        self.turnstile_site_key = settings.TURNSTILE_SITE_KEY
        self.turnstile_test_mode = settings.TURNSTILE_TEST_MODE
        self.turnstile_dev_bypass = settings.DEBUG and not self.turnstile_enabled

    def clean(self):
        if self.turnstile_enabled:
            token = self.data.get("cf-turnstile-response", "").strip()
            if not token:
                raise ValidationError("Please complete the human verification check.")

            try:
                verified = verify_turnstile_response(
                    token,
                    settings.TURNSTILE_SECRET_KEY,
                )
            except TurnstileUnavailable:
                raise ValidationError(
                    "Human verification is temporarily unavailable. Please try again."
                ) from None

            if not verified:
                raise ValidationError(
                    "Human verification could not be verified. Please try again."
                )

        return super().clean()
