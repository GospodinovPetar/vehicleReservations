from rest_framework import permissions
from rest_framework import permissions
from inventory.models import CustomUser


class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow admin users.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_admin


class IsManagerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow managers and admins.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_manager


class IsOwnerOrManagerOrAdmin(permissions.BasePermission):
    """
    Custom permission to allow users to access their own data,
    or managers/admins to access any data.
    """

    def has_object_permission(self, request, view, obj):
        # Admin and managers can access any object
        if request.user.is_manager:
            return True

        # Users can only access their own objects
        if hasattr(obj, 'user'):
            return obj.user == request.user

        # If the object IS a user, check if it's the same user
        if isinstance(obj, type(request.user)):
            return obj == request.user

        return False


class IsActiveUser(permissions.BasePermission):
    """
    Permission to check if user is active and not blocked.
    """

    def has_permission(self, request, view):
        return (
                request.user and
                request.user.is_authenticated and
                request.user.is_active and
                not request.user.is_blocked
        )


class RoleBasedPermission(permissions.BasePermission):
    """
    Base permission class for role-based access control.
    Define required_roles in your view to specify which roles can access it.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_blocked:
            return False

        # Get required roles from view
        required_roles = getattr(view, 'required_roles', [])
        if not required_roles:
            return True  # No specific role required

        return request.user.role in required_roles


class VehiclePermission(permissions.BasePermission):
    """
    Permission for vehicle management:
    - Managers and Admins can create, update, delete vehicles
    - Users can only view vehicles
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_blocked:
            return False

        # Read permissions for any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions only for managers and admins
        return request.user.is_manager


class ReservationPermission(permissions.BasePermission):
    """
    Permission for reservation management:
    - All authenticated users can create reservations
    - Users can only manage their own reservations
    - Managers and Admins can manage all reservations
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_blocked:
            return False

        return True

    def has_object_permission(self, request, view, obj):
        # Managers and admins can access any reservation
        if request.user.is_manager:
            return True

        # Users can only access their own reservations
        return obj.user == request.user
