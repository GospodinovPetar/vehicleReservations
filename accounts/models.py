from django.core.exceptions import ValidationError
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
import re
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    """Manager for CustomUser providing user and superuser creation."""

    def create_user(self, username, email=None, password=None, **extra_fields):
        """Create and return a regular user."""
        if not username:
            raise ValueError("The Username must be set")
        email = self.normalize_email(email)
        extra_fields.setdefault("is_active", True)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        """Create and return a superuser with admin role."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "admin")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(username, email, password, **extra_fields)


class CustomUser(AbstractUser):
    """Custom user model with role, phone, and blocking support."""

    ROLE_CHOICES = [
        ("user", "User"),
        ("manager", "Manager"),
        ("admin", "Admin"),
    ]

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="user")
    phone = models.CharField(max_length=15, blank=True, null=True, unique=True)
    is_blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    def __str__(self):
        """Return a readable representation with role."""
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        """True if user is an active admin."""
        return self.role == "admin" and not self.is_blocked

    @property
    def is_manager(self):
        """True if user is manager or admin and not blocked."""
        return self.role in ["manager", "admin"] and not self.is_blocked

    @property
    def can_manage_vehicles(self):
        """Permission flag for managing vehicles."""
        return self.is_manager

    @property
    def can_manage_users(self):
        """Permission flag for managing users."""
        return self.is_admin

    def clean(self):
        """Validate fields (e.g., phone format)."""
        super().clean()
        if self.phone and not re.match(r"^\+?[\d\s\-()]{10,15}$", self.phone):
            raise ValidationError({"phone": "Invalid phone number format"})

    def save(self, *args, **kwargs):
        """Validate then persist the user."""
        self.full_clean()
        super().save(*args, **kwargs)


class PendingRegistration(models.Model):
    """Stash registration data until email is verified."""

    username = models.CharField(max_length=150, db_index=True)
    email = models.EmailField(db_index=True, unique=True)
    first_name = models.CharField(max_length=150, blank=True, default="")
    last_name = models.CharField(max_length=150, blank=True, default="")
    phone = models.CharField(max_length=15, blank=True, null=True)
    password_hash = models.CharField(max_length=255)
    role = models.CharField(max_length=10, default="user")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        """Model metadata: add indexes for lookups."""
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["username"]),
        ]

    def is_expired(self) -> bool:
        """Return True if the registration has expired."""
        return timezone.now() > self.expires_at

    @classmethod
    def start(
        cls,
        *,
        username,
        email,
        first_name,
        last_name,
        phone,
        password_hash,
        ttl_hours: int = 24,
    ):
        """Create or replace a pending registration with a TTL."""
        cls.objects.filter(email=email).delete()
        cls.objects.filter(username=username).delete()
        return cls.objects.create(
            username=username,
            email=email,
            first_name=first_name or "",
            last_name=last_name or "",
            phone=phone or None,
            password_hash=password_hash,
            role="user",
            expires_at=timezone.now() + timezone.timedelta(hours=ttl_hours),
        )
