from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import Vehicle, Location, Reservation, ReservationStatus
from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.openapi import OpenApiTypes
from .models import CustomUser
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer, UserProfileSerializer,
    UserListSerializer, UserManagementSerializer, ChangePasswordSerializer
)
from .permissions import IsAdminUser, IsManagerOrAdmin, IsOwnerOrManagerOrAdmin, IsActiveUser


# -----------------------------
# Helpers
# -----------------------------
def parse_iso_date(value):
    """Return a date from YYYY-MM-DD string or None on error."""
    try:
        if value:
            return date.fromisoformat(value)
        return None
    except Exception:
        return None


def compute_total(days_count, price_per_day):
    """Pricing: total = days × daily price."""
    if price_per_day is None:
        return Decimal("0.00")
    daily = Decimal(str(price_per_day))
    total = daily * Decimal(int(days_count))
    return total.quantize(Decimal("0.01"))


# -----------------------------
# Views
# -----------------------------
def home(request):
    locations_qs = Location.objects.all()
    context = {"locations": locations_qs}
    return render(request, "home.html", context)


def search(request):
    start_param = request.GET.get("start")
    end_param = request.GET.get("end")
    pickup_location_id = request.GET.get("pickup_location")
    return_location_id = request.GET.get("return_location")

    locations_qs = Location.objects.all()
    context = {
        "locations": locations_qs,
        "start": start_param,
        "end": end_param,
        "pickup_location": pickup_location_id,
        "return_location": return_location_id,
    }

    # both dates required
    if not start_param or not end_param:
        messages.error(request, "Please select both start and end dates.")
        return render(request, "home.html", context)

    start_date = parse_iso_date(start_param)
    end_date = parse_iso_date(end_param)
    if start_date is None or end_date is None or end_date <= start_date:
        messages.error(request, "Start date must be before end date.")
        return render(request, "home.html", context)

    # optional location filters
    pickup_location = None
    if pickup_location_id:
        pickup_location = Location.objects.filter(id=pickup_location_id).first()

    return_location = None
    if return_location_id:
        return_location = Location.objects.filter(id=return_location_id).first()

    # available vehicles for that window (and locations if provided)
    available_ids_qs = Reservation.available_vehicle_ids(
        start_date, end_date, pickup_location, return_location
    )
    vehicles_qs = Vehicle.objects.filter(id__in=available_ids_qs)

    # build a plain list of results
    results = []
    days_count = (end_date - start_date).days
    for v in vehicles_qs:
        total_cost = compute_total(days_count, v.price_per_day)
        row = {
            "vehicle": v,
            "quote": {
                "days": int(days_count),
                "total": float(total_cost),
                "currency": "EUR",
            },
        }
        results.append(row)

        available_ids_qs = Reservation.available_vehicle_ids(
            start_date, end_date, pickup_location, return_location
        )

        vehicles_qs = Vehicle.objects.filter(id__in=available_ids_qs).prefetch_related(
            "available_pickup_locations", "available_return_locations"
        )

    context["results"] = results
    return render(request, "home.html", context)


@login_required
@require_http_methods(["POST"])
def reserve(request):
    data = request.POST

    vehicle = get_object_or_404(Vehicle, pk=data.get("vehicle"))
    start_date = parse_iso_date(data.get("start"))
    end_date = parse_iso_date(data.get("end"))

    if start_date is None or end_date is None or end_date <= start_date:
        messages.error(request, "Start date must be before end date.")
        return redirect(
            f"/search/?start={data.get('start') or ''}&end={data.get('end') or ''}"
        )

    # Try posted IDs first
    pickup_location = None
    if data.get("pickup_location"):
        pickup_location = get_object_or_404(Location, pk=data.get("pickup_location"))
    else:
        # fall back to first allowed pickup location
        pickup_location = vehicle.available_pickup_locations.first()

    return_location = None
    if data.get("return_location"):
        return_location = get_object_or_404(Location, pk=data.get("return_location"))
    else:
        # fall back to first allowed return location
        return_location = vehicle.available_return_locations.first()

    if pickup_location is None or return_location is None:
        messages.error(
            request, "This vehicle has no configured pickup/return locations."
        )
        return redirect(
            f"/search/?start={data.get('start') or ''}&end={data.get('end') or ''}"
        )

    # Enforce allow-lists
    if not vehicle.available_pickup_locations.filter(pk=pickup_location.pk).exists():
        messages.error(
            request, "Selected pickup location is not available for this vehicle."
        )
        return redirect(
            f"/search/?start={data.get('start') or ''}&end={data.get('end') or ''}"
        )

    if not vehicle.available_return_locations.filter(pk=return_location.pk).exists():
        messages.error(
            request, "Selected return location is not available for this vehicle."
        )
        return redirect(
            f"/search/?start={data.get('start') or ''}&end={data.get('end') or ''}"
        )

    reservation = Reservation(
        user=request.user,
        vehicle=vehicle,
        pickup_location=pickup_location,
        return_location=return_location,
        start_date=start_date,
        end_date=end_date,
        status=ReservationStatus.RESERVED,
    )

    try:
        reservation.full_clean()
    except Exception as exc:
        messages.error(request, str(exc))
        return redirect(
            f"/search/?start={data.get('start') or ''}&end={data.get('end') or ''}"
        )

    reservation.save()
    messages.success(request, "Reservation created.")
    return redirect("/reservations/")


@login_required
def reservations(request):
    user_reservations = (
        Reservation.objects.filter(user=request.user)
        .select_related("vehicle", "pickup_location", "return_location")
        .all()
    )
    context = {"reservations": user_reservations}
    return render(request, "reservations.html", context)


@login_required
@require_http_methods(["POST"])
def reject_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk, user=request.user)
    if reservation.status not in (
        ReservationStatus.RESERVED,
        ReservationStatus.AWAITING_PICKUP,
    ):
        messages.error(
            request, "Only new or awaiting-pickup reservations can be rejected."
        )
        return redirect("/reservations/")
    reservation.status = ReservationStatus.REJECTED
    reservation.save(update_fields=["status"])
    messages.success(request, "Reservation rejected.")
    return redirect("/reservations/")


# -------- auth views --------
@require_http_methods(["GET", "POST"])
def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            login(request, new_user)
            messages.success(
                request, "Your account was created and you are now logged in."
            )
            return redirect("/")
        messages.error(request, "Please correct the errors below.")
    else:
        form = UserCreationForm()
    return render(request, "auth.html", {"form": form, "title": "Register"})


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            next_url = request.GET.get("next")
            if not next_url:
                next_url = "/"
            messages.success(request, "You are now logged in.")
            return redirect(next_url)
        messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm(request)
    return render(request, "auth.html", {"form": form, "title": "Login"})


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("/")


class UserRegistrationView(generics.CreateAPIView):
    """
    User registration endpoint. Anyone can register as a regular user.
    """
    queryset = CustomUser.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        summary="Register a new user",
        description="Create a new user account. New users are assigned 'user' role by default.",
        responses={201: UserProfileSerializer}
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                'message': 'User registered successfully',
                'user': UserProfileSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom login view that returns user info along with tokens.
    """
    serializer_class = UserLoginSerializer

    @extend_schema(
        summary="User login",
        description="Login with username and password to get JWT tokens.",
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']

            # Generate tokens
            refresh = RefreshToken.for_user(user)
            access_token = refresh.access_token

            return Response({
                'access_token': str(access_token),
                'refresh_token': str(refresh),
                'user': UserProfileSerializer(user).data,
                'message': 'Login successful'
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    Get and update user profile. Users can only access their own profile.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsActiveUser]

    def get_object(self):
        return self.request.user

    @extend_schema(
        summary="Get user profile",
        description="Get the current authenticated user's profile information."
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Update user profile",
        description="Update the current authenticated user's profile information."
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)


class ChangePasswordView(APIView):
    """
    Change user password.
    """
    permission_classes = [IsActiveUser]

    @extend_schema(
        summary="Change password",
        description="Change the current user's password.",
        request=ChangePasswordSerializer
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({'message': 'Password changed successfully'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserLogoutView(APIView):
    """
    Logout user by blacklisting the refresh token.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="User logout",
        description="Logout the current user and blacklist the refresh token."
    )
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            logout(request)
            return Response({'message': 'Logged out successfully'})
        except Exception as e:
            return Response({'error': 'Invalid token'}, status=status.HTTP_400_BAD_REQUEST)


# Admin-only views for user management
class UserListView(generics.ListAPIView):
    """
    List all users (Admin only).
    """
    queryset = CustomUser.objects.all().order_by('-date_joined')
    serializer_class = UserListSerializer
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="List all users",
        description="Get a list of all users in the system. Admin access required.",
        parameters=[
            OpenApiParameter(
                name='role',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Filter by user role (user, manager, admin)'
            ),
            OpenApiParameter(
                name='is_blocked',
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description='Filter by blocked status'
            ),
        ]
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        role = self.request.query_params.get('role')
        is_blocked = self.request.query_params.get('is_blocked')

        if role:
            queryset = queryset.filter(role=role)
        if is_blocked is not None:
            is_blocked_bool = is_blocked.lower() == 'true'
            queryset = queryset.filter(is_blocked=is_blocked_bool)

        return queryset


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, or delete a specific user (Admin only).
    """
    queryset = CustomUser.objects.all()
    serializer_class = UserManagementSerializer
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Get user details",
        description="Get detailed information about a specific user. Admin access required."
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Update user",
        description="Update a user's information including role and blocked status. Admin access required."
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @extend_schema(
        summary="Delete user",
        description="Delete a user from the system. Admin access required."
    )
    def delete(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            return Response(
                {'error': 'You cannot delete your own account'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().delete(request, *args, **kwargs)


class UserCreateView(generics.CreateAPIView):
    """
    Create a new user with specific role (Admin only).
    """
    queryset = CustomUser.objects.all()
    serializer_class = UserManagementSerializer
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Create user",
        description="Create a new user with specified role. Admin access required."
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class BlockUserView(APIView):
    """
    Block/unblock a user (Admin only).
    """
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Block/Unblock user",
        description="Block or unblock a user account. Admin access required.",
        parameters=[
            OpenApiParameter(
                name='action',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description='Action to perform: "block" or "unblock"',
                required=True
            )
        ]
    )
    def post(self, request, pk):
        user = get_object_or_404(CustomUser, pk=pk)
        action = request.query_params.get('action', '').lower()

        if user == request.user:
            return Response(
                {'error': 'You cannot block/unblock your own account'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if action == 'block':
            user.is_blocked = True
            message = f'User {user.username} has been blocked'
        elif action == 'unblock':
            user.is_blocked = False
            message = f'User {user.username} has been unblocked'
        else:
            return Response(
                {'error': 'Invalid action. Use "block" or "unblock"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.save()
        return Response({
            'message': message,
            'user': UserListSerializer(user).data
        })


class UserStatsView(APIView):
    """
    Get user statistics (Admin only).
    """
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Get user statistics",
        description="Get statistics about users in the system. Admin access required."
    )
    def get(self, request):
        stats = {
            'total_users': CustomUser.objects.count(),
            'active_users': CustomUser.objects.filter(is_active=True, is_blocked=False).count(),
            'blocked_users': CustomUser.objects.filter(is_blocked=True).count(),
            'users_by_role': {
                'user': CustomUser.objects.filter(role='user').count(),
                'manager': CustomUser.objects.filter(role='manager').count(),
                'admin': CustomUser.objects.filter(role='admin').count(),
            }
        }
        return Response(stats)
