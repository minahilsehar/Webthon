from django.contrib.auth import views as auth_views
from django.urls import path

from .controllers import save_theme
from .controllers.profiles import my_profile, user_photo
from .forms.turnstile import TurnstileAuthenticationForm

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(
            authentication_form=TurnstileAuthenticationForm,
            template_name="accounts/login.html",
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("theme/", save_theme, name="save_theme"),
    path("profile/", my_profile, name="my_profile"),
    path("photo/<str:token>/", user_photo, name="user_photo"),
]
