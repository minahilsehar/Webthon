from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST

from ..models import User
from ..services.theme import update_theme


@require_POST
@login_required
def save_theme(request):
    theme = request.POST.get("theme")
    if theme not in User.Theme.values:
        return HttpResponseBadRequest("Invalid theme.")

    update_theme(request.user, theme)
    return HttpResponse(status=204)
