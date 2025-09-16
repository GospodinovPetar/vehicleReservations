from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
import getpass

User = get_user_model()


class Command(BaseCommand):
    help = "Create an admin user"

    def add_arguments(self, parser):
        parser.add_argument("--username", type=str, help="Admin username")
        parser.add_argument("--email", type=str, help="Admin email")
        parser.add_argument("--password", type=str, help="Admin password")

    def handle(self, *args, **options):
        while True:
            username = input("Username: ").strip()
            if not username:
                self.stdout.write(self.style.ERROR("Username cannot be blank."))
                continue
            if User.objects.filter(username=username).exists():
                self.stdout.write(self.style.ERROR("This username already exists."))
                continue
            break

        email = options.get("email") or input("Email: ")

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

        admin_user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            role="admin",
            is_staff=True,
            is_superuser=True,
        )

        self.stdout.write(
            self.style.SUCCESS(f'Admin user "{username}" created successfully')
        )
