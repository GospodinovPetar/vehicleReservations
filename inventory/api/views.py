from rest_framework import generics, permissions
from django.contrib.auth import get_user_model
from .serializers import UserSerializer
from .permissions import IsAdmin

User = get_user_model()


# User Registration (open to all)
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]


# Admin can list all users
class UserListView(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated & IsAdmin]


# Admin can delete users
class UserDeleteView(generics.DestroyAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated & IsAdmin]


# Admin can block users
from rest_framework.response import Response
from rest_framework import status


class UserBlockView(generics.UpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated & IsAdmin]

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        user.is_blocked = True
        user.save()
        return Response({"message": f"User {user.username} has been blocked."}, status=status.HTTP_200_OK)
