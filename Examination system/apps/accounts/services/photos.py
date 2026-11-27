import hashlib
import io

from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.signing import TimestampSigner
from django.db import transaction
from django.urls import reverse

from ..models import AccountAuditLog, User, UserPhoto


MAX_UPLOAD_BYTES = 1024 * 1024
MAX_IMAGE_SIDE = 4096
MAX_IMAGE_PIXELS = 16_000_000
MAX_PROCESSED_BYTES = 10 * 1024
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
PHOTO_SIGNER = TimestampSigner(salt="accounts.user_photo")


def user_photo_url(user):
    try:
        user.photo.pk
    except UserPhoto.DoesNotExist:
        return None
    token = PHOTO_SIGNER.sign(str(user.pk))
    return reverse("user_photo", kwargs={"token": token})


def process_profile_photo(uploaded_file):
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        raise ValidationError("Profile photos must be 1 MB or smaller.")

    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            if image.format not in ALLOWED_FORMATS:
                raise ValidationError("Use a JPEG, PNG, or WebP image.")
            if (
                image.width > MAX_IMAGE_SIDE
                or image.height > MAX_IMAGE_SIDE
                or image.width * image.height > MAX_IMAGE_PIXELS
            ):
                raise ValidationError("Image dimensions must not exceed 4096 by 4096.")
            image.verify()

        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            image = ImageOps.exif_transpose(image)
            if "A" in image.getbands():
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")

            image = ImageOps.fit(
                image,
                (160, 160),
                method=Image.Resampling.LANCZOS,
            )
            for quality in (82, 74, 66, 58, 50):
                output = io.BytesIO()
                image.save(
                    output,
                    format="JPEG",
                    quality=quality,
                    optimize=True,
                    progressive=True,
                )
                if output.tell() <= MAX_PROCESSED_BYTES:
                    return output.getvalue()

            image = ImageOps.fit(
                image,
                (128, 128),
                method=Image.Resampling.LANCZOS,
            )
            output = io.BytesIO()
            image.save(
                output,
                format="JPEG",
                quality=50,
                optimize=True,
                progressive=True,
            )
            if output.tell() <= MAX_PROCESSED_BYTES:
                return output.getvalue()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValidationError(
            "The upload is not a valid, decodable JPEG, PNG, or WebP image."
        ) from error

    raise ValidationError(
        "This image cannot be re-encoded to the 10 KB profile-photo limit."
    )


@transaction.atomic
def update_profile_photo(actor, user, uploaded_file):
    _require_administrator(actor)
    image_bytes = process_profile_photo(uploaded_file)
    locked_user = User.objects.select_for_update().get(pk=user.pk)
    previous = UserPhoto.objects.filter(user=locked_user).first()
    previous_digest = (
        hashlib.sha256(bytes(previous.image)).hexdigest() if previous else None
    )
    current, _created = UserPhoto.objects.update_or_create(
        user=locked_user,
        defaults={"image": image_bytes},
    )
    AccountAuditLog.objects.create(
        actor=actor,
        target_user=locked_user,
        action=AccountAuditLog.Action.PROFILE_UPDATED,
        resource_type="photo",
        resource_id=str(locked_user.pk),
        details={
            "old_sha256": previous_digest,
            "new_sha256": hashlib.sha256(image_bytes).hexdigest(),
        },
    )
    return current


def _require_administrator(actor):
    if (
        not actor.is_authenticated
        or not actor.is_active
        or actor.role != User.Role.ADMIN
    ):
        raise PermissionDenied("Only administrators may manage profile details.")
