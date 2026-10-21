from django import forms
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from accounts.models import StoreUser, ensure_owner_store_user
from stores.models import Store
from .user_sync_notice import notify_user_sync_required


class OwnerAccountForm(forms.Form):
    username = forms.CharField(label="اسم المستخدم", max_length=StoreUser._meta.get_field("identifier").max_length,
                               validators=User._meta.get_field("username").validators,
                               widget=forms.TextInput(attrs={"autocomplete": "username"}))
    current_password = forms.CharField(label="كلمة المرور الحالية", strip=False,
                                      widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    new_password = forms.CharField(label="كلمة المرور الجديدة", required=False, strip=False,
                                  widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                  help_text="اتركها فارغة إذا أردت تغيير اسم المستخدم فقط.")
    confirmation = forms.CharField(label="تأكيد كلمة المرور الجديدة", required=False, strip=False,
                                  widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner

    def clean_current_password(self):
        value = self.cleaned_data["current_password"]
        if not self.owner.check_password(value):
            raise forms.ValidationError("كلمة المرور الحالية غير صحيحة.")
        return value

    def clean_username(self):
        value = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=value).exclude(pk=self.owner.pk).exists():
            raise forms.ValidationError("اسم المستخدم مستخدم مسبقاً.")
        if StoreUser.objects.filter(store__owner=self.owner, identifier__iexact=value).exclude(auth_user=self.owner).exists():
            raise forms.ValidationError("اسم المستخدم مستخدم من حساب آخر ضمن متاجرك.")
        return value

    def clean(self):
        data = super().clean()
        password = data.get("new_password", "")
        if password != data.get("confirmation", ""):
            self.add_error("confirmation", "كلمتا المرور غير متطابقتين.")
        if password:
            try:
                validate_password(password, self.owner)
            except ValidationError as error:
                self.add_error("new_password", error)
            others = StoreUser.objects.filter(store__owner=self.owner).exclude(auth_user=self.owner)
            if any(user.check_password(password) for user in others):
                self.add_error("new_password", "كلمة المرور مستخدمة من حساب آخر ضمن متاجرك.")
        return data


def save_owner_account(store, owner, cleaned_data):
    """Apply validated credentials inside the caller's transaction."""
    owner.username = cleaned_data["username"]
    if cleaned_data["new_password"]:
        owner.set_password(cleaned_data["new_password"])
    owner.save(update_fields=["username", "password"])
    store.owner = owner
    ensure_owner_store_user(store)
    profiles = StoreUser.objects.filter(auth_user=owner, store__owner=owner)
    for profile in profiles:
        profile.identifier = owner.username
        profile.password = owner.password
        profile.save(update_fields=["identifier", "password"])


@never_cache
@sensitive_post_parameters("password", "current_password", "new_password", "confirmation")
@require_http_methods(["GET", "POST"])
def owner_account(request, store_slug):
    # Account access is independent of storefront activation; only its owner may edit it.
    store = get_object_or_404(Store.objects.select_related("owner"), slug=store_slug)
    if not request.user.is_authenticated:
        form = AuthenticationForm(request, data=request.POST if request.method == "POST" else None)
        if request.method == "POST" and form.is_valid():
            if form.get_user().pk != store.owner_id:
                form.add_error(None, "تسجيل الدخول متاح لمدير هذا المتجر فقط.")
            else:
                login(request, form.get_user())
                request.session.pop("store_user_id", None)
                return redirect("dashboard:owner_account", store_slug=store.slug)
        return render(request, "dashboard/owner_account.html", {"store": store, "form": form, "account_login": True})
    if request.user.pk != store.owner_id:
        raise Http404

    form = OwnerAccountForm(owner=store.owner, initial={"username": store.owner.username})
    if request.method == "POST":
        try:
            with transaction.atomic():
                owner = User.objects.select_for_update().get(pk=store.owner_id)
                form = OwnerAccountForm(request.POST, owner=owner)
                if form.is_valid():
                    save_owner_account(store, owner, form.cleaned_data)
                    update_session_auth_hash(request, owner)
                    messages.success(request, "تم تحديث بيانات حسابك.")
                    notify_user_sync_required(request)
                    return redirect("dashboard:owner_account", store_slug=store.slug)
        except IntegrityError:
            form.add_error("username", "اسم المستخدم مستخدم مسبقاً. اختر اسماً آخر.")
    return render(request, "dashboard/owner_account.html", {"store": store, "form": form})
