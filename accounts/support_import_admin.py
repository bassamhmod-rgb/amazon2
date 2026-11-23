import uuid
import re

from django import forms
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse

from .models import SupportQuestion
from .support_docx import SupportDocxError, parse_support_docx, question_key

PREVIEW_KEY = 'support_docx_preview'


class SupportDocxForm(forms.Form):
    document = forms.FileField(label='ملف الأسئلة والأجوبة (.docx)',
                               widget=forms.ClearableFileInput(attrs={'accept': '.docx'}))

    def clean_document(self):
        document = self.cleaned_data['document']
        if not document.name.lower().endswith('.docx'):
            raise forms.ValidationError('اختر ملف Word بصيغة .docx.')
        if document.size > 5 * 1024 * 1024:
            raise forms.ValidationError('حجم الملف يجب ألا يتجاوز 5 ميغابايت.')
        return document


def import_support_docx(model_admin, request):
    if not (model_admin.has_add_permission(request) and model_admin.has_change_permission(request)):
        raise PermissionDenied
    url = reverse('admin:accounts_supportquestion_changelist')
    form = SupportDocxForm()
    preview = None
    error = None
    if request.method == 'POST' and request.POST.get('action') == 'confirm':
        stored = request.session.get(PREVIEW_KEY)
        if not stored or request.POST.get('token') != stored['token']:
            error = 'انتهت المعاينة أو تم استيرادها بالفعل. اختر الملف مجدداً.'
        else:
            created = updated = unchanged = 0
            with transaction.atomic():
                existing = list(SupportQuestion.objects.select_for_update().all())
                by_question = {}
                for obj in existing:
                    by_question.setdefault(question_key(obj.question), obj)
                order = max((obj.sort_order for obj in existing), default=0)
                for item in stored['items']:
                    obj = by_question.get(question_key(item['question']))
                    if obj:
                        if obj.answer != item['answer']:
                            obj.answer = item['answer']
                            obj.save(update_fields=['answer'])
                            model_admin.log_change(request, obj, 'تحديث الإجابة من ملف Word')
                            updated += 1
                        else:
                            unchanged += 1
                    else:
                        order += 1
                        obj = SupportQuestion.objects.create(**item, sort_order=order, is_active=True)
                        model_admin.log_addition(request, obj, 'استيراد من ملف Word')
                        created += 1
            request.session.pop(PREVIEW_KEY, None)
            model_admin.message_user(request,
                f'اكتمل الاستيراد: {created} سؤال جديد، {updated} إجابة محدثة، {unchanged} دون تغيير.')
            return redirect(url)
    elif request.method == 'POST':
        request.session.pop(PREVIEW_KEY, None)
        form = SupportDocxForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                items, warnings = parse_support_docx(form.cleaned_data['document'].read())
                existing = {question_key(q.question): q for q in SupportQuestion.objects.all()}
                for index, item in enumerate(items, 1):
                    old = existing.get(question_key(item['question']))
                    if old:
                        removed_links = [link for link in re.findall(r'https?://[^\s<>]+', old.answer)
                                         if link not in item['answer']]
                        if removed_links:
                            warnings.append(f'السؤال {index}: الإجابة الجديدة لا تحتوي على هذه الروابط الموجودة حالياً: '
                                            + ' ، '.join(removed_links))
                preview = {'token': uuid.uuid4().hex, 'items': items, 'warnings': warnings}
                request.session[PREVIEW_KEY] = preview
            except SupportDocxError as exc:
                form.add_error('document', str(exc))
    if preview:
        existing = {question_key(q.question): q for q in SupportQuestion.objects.all()}
        rows = []
        for item in preview['items']:
            obj = existing.get(question_key(item['question']))
            status = 'إضافة سؤال جديد' if obj is None else (
                'دون تغيير' if obj.answer == item['answer'] else 'تحديث الإجابة')
            rows.append({**item, 'status': status, 'inactive': obj is not None and not obj.is_active})
    else:
        rows = []
    context = {
        **model_admin.admin_site.each_context(request),
        'opts': model_admin.model._meta,
        'title': 'استيراد الأسئلة الشائعة من Word',
        'form': form, 'preview': preview, 'rows': rows, 'list_url': url, 'error': error,
    }
    return TemplateResponse(request, 'admin/accounts/supportquestion/import_docx.html', context)
