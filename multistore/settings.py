from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "change-me"

def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


DEBUG = _env_bool("DJANGO_DEBUG", True)


def _env_list(name, default):
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


ADMINS = [("Admin", "admin@example.com")]
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "file": {
            "level": "ERROR",
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "django_errors.log",

        },
    },
    "loggers": {
        "django": {
            "handlers": ["file"],
            "level": "ERROR",
            "propagate": True,
        },
    },
}

ALLOWED_HOSTS = [
    "amazon2-dwsb.onrender.com",
    "www.amazon2-dwsb.onrender.com",
    "amazonsyria.com",
    "www.amazonsyria.com",
    "127.0.0.1",
    "localhost",
]

ALLOWED_HOSTS += _env_list("DJANGO_ALLOWED_HOSTS", [])

CSRF_TRUSTED_ORIGINS = [
    "https://amazon2-dwsb.onrender.com",
    "https://www.amazon2-dwsb.onrender.com",
    "https://amazonsyria.com",
    "https://www.amazonsyria.com",
]
CSRF_TRUSTED_ORIGINS += _env_list("DJANGO_CSRF_TRUSTED_ORIGINS", [])

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "core.apps.CoreConfig",
    "accounts.apps.AccountsConfig",
    "stores",
    "products",
    "cart",
    "orders",
    "loyalty",
    "dashboard",
    'rest_framework',
    "mobile_sync.apps.MobileSyncConfig",

]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "mobile_sync.middleware.MobileDevCorsMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "multistore.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "file_charset": "utf-8",
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "stores.context_processors.current_store",
                "orders.context_processors.merchant_notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "multistore.wsgi.application"
#مشان دالة الخطأ
CSRF_FAILURE_VIEW = "accounts.views.csrf_failure"
#

import dj_database_url


if os.getenv("DATABASE_URL"):
    DATABASES = {
        "default": dj_database_url.parse(
            os.environ["DATABASE_URL"],
            conn_max_age=600,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": os.getenv("DATABASE_ENGINE", "django.db.backends.postgresql"),
            "NAME": os.getenv("DATABASE_NAME", "alaman_pos"),
            "USER": os.getenv("DATABASE_USER", "postgres"),
            "PASSWORD": os.getenv("DATABASE_PASSWORD", ""),
            "HOST": os.getenv("DATABASE_HOST", "127.0.0.1"),
            "PORT": os.getenv("DATABASE_PORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("DATABASE_CONN_MAX_AGE", "60")),
        }
    }
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000
AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.getenv("DJANGO_MEDIA_ROOT", BASE_DIR / "media"))
SERVE_MEDIA_FILES = _env_bool("DJANGO_SERVE_MEDIA_FILES", DEBUG)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DEFAULT_CHARSET = "utf-8"
FILE_CHARSET = "utf-8"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "/accounts/redirect/"
LOGOUT_REDIRECT_URL = "core:index"
