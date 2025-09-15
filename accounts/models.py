# ---------------
# Users
# ---------------

from django.conf import settings
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import Q
import re


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
        extra_fields.setdefault("role", "admin")  # force role=admin

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
    phone = models.CharField(max_length=15, blank=True, null=True)
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
