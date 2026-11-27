from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST

from .models import User


@require_POST
@login_required
def save_theme(request):
    theme = request.POST.get("theme")
    if theme not in User.Theme.values:
        return HttpResponseBadRequest("Invalid theme.")

    request.user.theme = theme
    request.user.save(update_fields=["theme"])
    return HttpResponse(status=204)
