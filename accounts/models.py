# ---------------
# Users
# ---------------

from django.conf import settings
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
import re


class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('manager', 'Manager'),
        ('admin', 'Admin'),
    ]

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='user')
    phone = models.CharField(max_length=15, blank=True, null=True)
    is_blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        return self.role == 'admin' and not self.is_blocked

    @property
    def is_manager(self):
        return self.role in ['manager', 'admin'] and not self.is_blocked

    @property
    def can_manage_vehicles(self):
        return self.is_manager

    @property
    def can_manage_users(self):
        return self.is_admin

    def clean(self):
        super().clean()
        if self.phone and not re.match(r'^\+?[\d\s\-()]{10,15}$', self.phone):
            raise ValidationError({'phone': 'Invalid phone number format'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
