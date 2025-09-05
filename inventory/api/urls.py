from django.urls import path
from .views import RegisterView, UserListView, UserDeleteView, UserBlockView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('users/', UserListView.as_view(), name='user-list'),  # admin only
    path('users/<int:pk>/delete/', UserDeleteView.as_view(), name='user-delete'),  # admin only
    path('users/<int:pk>/block/', UserBlockView.as_view(), name='user-block'),  # admin only
]
