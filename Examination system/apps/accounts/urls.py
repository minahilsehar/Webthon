from django.contrib.auth import views as auth_views
from django.urls import path

from .controllers import save_theme

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("theme/", save_theme, name="save_theme"),
]
