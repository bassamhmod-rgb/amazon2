from django.conf import settings
from django.contrib.auth import login, get_user_model
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.urls import path
from .urls import urlpatterns as regular_urls


def local_login(request):
    if settings.SETTINGS_MODULE != 'multistore.local_test_settings' or request.META.get('REMOTE_ADDR') not in ('127.0.0.1', '::1'):
        return HttpResponseForbidden()
    login(request, get_user_model().objects.get(username='localtester'))
    return redirect('/dashboard/local-test/')


def health(request):
    import os
    from django.db import connection, DatabaseError
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        database_ready = True
    except DatabaseError:
        database_ready = False
    return JsonResponse({'environment': 'alaman-local-test', 'version': 1,
        'database_ready': database_ready,
        'instance': os.environ['ALAMAN_LOCAL_TEST_INSTANCE'], 'pid': os.getpid()})


urlpatterns = [path('__local_test__/login/', local_login),
               path('__local_test__/health/', health)] + regular_urls
