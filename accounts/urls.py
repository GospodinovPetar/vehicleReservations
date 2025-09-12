from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("admin-dashboard/", views.admin_dashboard, name="admin-dashboard"),
    path("manager-dashboard/", views.manager_dashboard, name="manager-dashboard"),
    path("blocked/", views.blocked_view, name="blocked"),
]
