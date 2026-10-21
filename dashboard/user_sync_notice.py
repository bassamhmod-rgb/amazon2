from django.contrib import messages


USER_SYNC_NOTICE = (
    "قبل تسجيل الدخول إلى التطبيق بعد تعديل المستخدمين أو بيانات المدير، "
    "اضغط زر «مزامنة المتجر والمستخدمين» الموجود في شاشة الدخول، "
    "ثم سجّل الدخول بالبيانات الجديدة. إذا كنت داخل التطبيق، سجّل الخروج أولاً."
)


def notify_user_sync_required(request):
    messages.info(request, USER_SYNC_NOTICE, extra_tags="users-sync-required")
