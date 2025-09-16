from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
import getpass

User = get_user_model()


class Command(BaseCommand):
    help = "Create a manager user (interactive, like createsuperuser)."

    def handle(self, *args, **options):
        # Ask for username
        while True:
            username = input("Username: ").strip()
            if not username:
                self.stdout.write(self.style.ERROR("Username cannot be blank."))
                continue
            if User.objects.filter(username=username).exists():
                self.stdout.write(self.style.ERROR("This username already exists."))
                continue
            break

        # Ask for email
        email = input("Email: ").strip()

        # Ask for password twice
        while True:
            password = options.get("password") or getpass.getpass("Password: ")
            password2 = options.get("Password (again)") or getpass.getpass(
                "Password (again): "
            )

            if password != password2:
                self.stdout.write(self.style.ERROR("Passwords do not match."))
                continue

            try:
                validate_password(password)
            except ValidationError as e:
                self.stdout.write(self.style.ERROR("; ".join(e.messages)))
                continue

            break

        # Create manager user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            role="manager",
            is_staff=True,  # can access Django admin
            is_superuser=False,  # not a superuser
        )

        self.stdout.write(
            self.style.SUCCESS(f'Manager "{username}" created successfully.')
        )
