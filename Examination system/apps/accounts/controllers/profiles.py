import hashlib

from django.contrib.auth.decorators import login_required
from django.core.signing import BadSignature
from django.http import Http404, HttpResponse, HttpResponseNotModified
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from ..models import User, UserPhoto
from ..services.photos import PHOTO_SIGNER


@login_required
def my_profile(request):
    return render(
        request,
        "accounts/profile.html",
        {"profile_user": request.user},
    )


@require_GET
@login_required
def user_photo(request, token):
    try:
        user_id = int(PHOTO_SIGNER.unsign(token, max_age=24 * 60 * 60))
    except (BadSignature, ValueError) as error:
        raise Http404("Photo not found.") from error

    photo = get_object_or_404(
        UserPhoto.objects.select_related("user"),
        user_id=user_id,
    )
    target = photo.user
    viewer = request.user
    can_view = (
        viewer.role == User.Role.ADMIN
        or viewer.pk == target.pk
        or (
            viewer.role == User.Role.EXAMINER
            and target.role == User.Role.CANDIDATE
            and target.is_active
        )
    )
    if not can_view:
        raise Http404("Photo not found.")

    image_bytes = bytes(photo.image)
    etag = f'"{hashlib.sha256(image_bytes).hexdigest()}"'
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponseNotModified()
    else:
        response = HttpResponse(image_bytes, content_type="image/jpeg")
    response["ETag"] = etag
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
