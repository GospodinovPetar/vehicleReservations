from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # Auth
    path("register/", views.UserRegistrationView.as_view(), name="user-register"),
    path("login/", views.CustomTokenObtainPairView.as_view(), name="user-login"),
    path("logout/", views.UserLogoutView.as_view(), name="user-logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),

    # User profile
    path("profile/", views.UserProfileView.as_view(), name="user-profile"),
    path("change-password/", views.ChangePasswordView.as_view(), name="change-password"),

    # Admin-only user management
    path("admin/users/", views.UserListView.as_view(), name="admin-user-list"),
    path("admin/users/create/", views.UserCreateView.as_view(), name="admin-user-create"),
    path("admin/users/<int:pk>/", views.UserDetailView.as_view(), name="admin-user-detail"),
    path("admin/users/<int:pk>/block/", views.BlockUserView.as_view(), name="admin-user-block"),
    path("admin/stats/", views.UserStatsView.as_view(), name="admin-user-stats"),
]
