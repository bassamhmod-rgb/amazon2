"""Explicitly selected, loopback-only development settings. Never production."""
from .settings import *  # noqa

if os.environ.get('ALAMAN_LOCAL_TEST') != '1':
    raise RuntimeError('Local test settings require the local test launcher.')
runtime = Path(os.environ['ALAMAN_LOCAL_TEST_ROOT']).resolve()
DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql',
    'NAME': 'alaman_local_test', 'USER': 'alaman_local_test', 'PASSWORD': '',
    'HOST': '127.0.0.1', 'PORT': '55449'}}
DEBUG = True
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:8765', 'http://localhost:8765']
ROOT_URLCONF = 'multistore.local_test_urls'
MEDIA_ROOT = runtime / 'media'
STATIC_ROOT = runtime / 'static'
SECRET_KEY = 'local-test-only-not-for-production'
SESSION_COOKIE_NAME = 'alaman_local_test_session'
CSRF_COOKIE_NAME = 'alaman_local_test_csrf'
LOGGING['handlers']['file']['filename'] = runtime / 'django_errors.log'
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
