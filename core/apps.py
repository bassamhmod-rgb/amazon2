from copy import copy

from django.apps import AppConfig
from django.template import context as template_context


def _copy_base_context(self):
    duplicate = object.__new__(self.__class__)
    duplicate.__dict__ = self.__dict__.copy()
    duplicate.dicts = self.dicts[:]
    return duplicate


def _copy_context(self):
    duplicate = _copy_base_context(self)
    duplicate.render_context = copy(self.render_context)
    return duplicate


def patch_django_context_copy():
    """
    Django 4.2's Context.__copy__ path can break on newer Python runtimes.
    Replace it with a direct copy that preserves Django's expected state.
    """
    template_context.BaseContext.__copy__ = _copy_base_context
    template_context.Context.__copy__ = _copy_context

class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        patch_django_context_copy()
