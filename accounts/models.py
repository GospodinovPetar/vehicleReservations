from django.core.exceptions import ValidationError
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
import re
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError("The Username must be set")
        email = self.normalize_email(email)
        extra_fields.setdefault("is_active", True)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "admin")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(username, email, password, **extra_fields)


class CustomUser(AbstractUser):
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
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == "admin" and not self.is_blocked

    @property
    def is_manager(self):
        return self.role in ["manager", "admin"] and not self.is_blocked

    @property
    def can_manage_vehicles(self):
        return self.is_manager

    @property
    def can_manage_users(self):
        return self.is_admin

    def clean(self):
        super().clean()
        if self.phone and not re.match(r"^\+?[\d\s\-()]{10,15}$", self.phone):
            raise ValidationError({"phone": "Invalid phone number format"})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class PendingRegistration(models.Model):
    """
    Temporarily stores registration data so we don't create a CustomUser
    until the email is verified.
    """

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
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["username"]),
        ]

    def is_expired(self) -> bool:
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
