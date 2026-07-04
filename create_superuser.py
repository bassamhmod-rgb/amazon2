import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "multistore.settings")
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

USERNAME = "admin"
EMAIL = ""
PASSWORD = "0966836013"

if not User.objects.filter(username=USERNAME).exists():
    User.objects.create_superuser(
        username=USERNAME,
        email=EMAIL,
        password=PASSWORD,
    )
    print("✅ Superuser created.")
else:
    print("ℹ️ Superuser already exists.")