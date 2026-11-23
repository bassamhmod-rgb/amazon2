from io import BytesIO
from zipfile import ZipFile
from xml.sax.saxutils import escape

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .models import SupportQuestion
from .support_docx import SupportDocxError, parse_support_docx
from .support_import_admin import PREVIEW_KEY


def document(paragraphs, automatic_first=False, hyperlink=False):
    body = []
    for i, text in enumerate(paragraphs):
        numbering = '<w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr>' if automatic_first and i == 0 else ''
        runs = '<w:r>' + '<w:br/>'.join('<w:t>' + escape(line) + '</w:t>' for line in text.split('\n')) + '</w:r>'
        if hyperlink and i == len(paragraphs) - 1:
            runs += '<w:hyperlink r:id="video"><w:r><w:t>شاهد الفيديو</w:t></w:r></w:hyperlink>'
        body.append('<w:p>' + numbering + runs + '</w:p>')
    out = BytesIO()
    with ZipFile(out, 'w') as archive:
        archive.writestr('word/document.xml',
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>'
            + ''.join(body) + '</w:body></w:document>')
        if hyperlink:
            archive.writestr('word/_rels/document.xml.rels',
                '<Relationships><Relationship Id="video" Target="https://youtu.be/demo"/></Relationships>')
    return out.getvalue()


class SupportDocxParserTests(SimpleTestCase):
    def test_automatic_arabic_numbering_soft_breaks_and_hyperlinks(self):
        items, warnings = parse_support_docx(document([
            'كيف أبدأ؟', 'إجابة\nتكملة', '٢- كيف أزامن؟', 'شرح'
        ], automatic_first=True, hyperlink=True))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0], {'question': 'كيف أبدأ؟', 'answer': 'إجابة\nتكملة'})
        self.assertIn('https://youtu.be/demo', items[1]['answer'])
        self.assertEqual(warnings, [])

    def test_numbered_answer_steps_stay_in_answer(self):
        items, _ = parse_support_docx(document(['1- كيف أبدأ؟', '1- اضغط الإعدادات\n2- اختر المتجر', '2- كيف أطبع؟', 'جواب']))
        self.assertEqual(len(items), 2)
        self.assertIn('2- اختر المتجر', items[0]['answer'])

    def test_missing_mark_duplicate_number_and_placeholder_have_warnings(self):
        items, warnings = parse_support_docx(document([
            '36- كيف أبدأ؟', 'إجابة', '36- كيف أطبع؟', 'جواب', '37- كيف أزامن', 'رابط فيديو'
        ]))
        self.assertEqual(len(items), 3)
        self.assertEqual(len(warnings), 3)

    def test_invalid_empty_answer_duplicate_question_and_xml_entities_rejected(self):
        for data in [b'invalid', document(['1- كيف أبدأ؟']),
                     document(['1- كيف أبدأ؟', 'جواب', '2- كيف أبدأ؟', 'جواب'])]:
            with self.assertRaises(SupportDocxError):
                parse_support_docx(data)
        out = BytesIO()
        with ZipFile(out, 'w') as archive:
            archive.writestr('word/document.xml', '<!DOCTYPE test><test/>')
        with self.assertRaises(SupportDocxError):
            parse_support_docx(out.getvalue())


class SupportDocxAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('faqimporter', password='test-only')
        self.client.force_login(self.user)
        self.url = reverse('admin:accounts_supportquestion_import_word')

    def upload(self, data):
        return self.client.post(self.url, {'document': SimpleUploadedFile('faq.docx', data)})

    def test_preview_then_confirm_updates_without_deletion_or_reactivation_and_replay(self):
        hidden = SupportQuestion.objects.create(question='كيف أبدأ؟', answer='قديم', sort_order=4, is_active=False)
        untouched = SupportQuestion.objects.create(question='سؤال آخر', answer='يبقى', sort_order=8)
        response = self.upload(document(['1- كيف أبدأ؟', 'جواب جديد', '2- كيف أطبع؟', 'https://youtu.be/demo']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'لم تُحفظ بعد')
        self.assertEqual(SupportQuestion.objects.count(), 2)
        hidden.refresh_from_db()
        self.assertEqual(hidden.answer, 'قديم')
        token = self.client.session[PREVIEW_KEY]['token']
        response = self.client.post(self.url, {'action': 'confirm', 'token': token})
        self.assertEqual(response.status_code, 302)
        hidden.refresh_from_db()
        self.assertEqual(hidden.answer, 'جواب جديد')
        self.assertFalse(hidden.is_active)
        self.assertEqual(hidden.sort_order, 4)
        self.assertTrue(SupportQuestion.objects.filter(pk=untouched.pk, answer='يبقى').exists())
        added = SupportQuestion.objects.get(question='كيف أطبع؟')
        self.assertEqual(added.sort_order, 9)
        self.assertTrue(added.is_active)
        self.client.post(self.url, {'action': 'confirm', 'token': token})
        self.assertEqual(SupportQuestion.objects.count(), 3)
        # Importing the same document again is also safe.
        self.upload(document(['1- كيف أبدأ؟', 'جواب جديد', '2- كيف أطبع؟', 'https://youtu.be/demo']))
        self.client.post(self.url, {'action': 'confirm', 'token': self.client.session[PREVIEW_KEY]['token']})
        self.assertEqual(SupportQuestion.objects.count(), 3)

    def test_bad_file_and_unconfirmed_request_do_not_write(self):
        response = self.upload(b'bad')
        self.assertContains(response, 'تعذّر قراءة الملف')
        self.assertNotIn(PREVIEW_KEY, self.client.session)
        self.client.post(self.url, {'action': 'confirm', 'token': 'forged'})
        self.assertEqual(SupportQuestion.objects.count(), 0)

    def test_permissions_and_preview_escaping(self):
        response = self.upload(document(['1- كيف أبدأ؟', '<script>alert(1)</script>']))
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        staff = get_user_model().objects.create_user('faqstaff', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.upload(document(['1- سؤال؟', 'جواب'])).status_code, 403)

    @override_settings(CSRF_FAILURE_VIEW='django.views.csrf.csrf_failure')
    def test_import_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(self.url, {'document': SimpleUploadedFile(
            'faq.docx', document(['1- كيف أبدأ؟', 'جواب']))})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(SupportQuestion.objects.count(), 0)

    def test_preview_warns_when_updated_answer_omits_existing_video(self):
        SupportQuestion.objects.create(question='كيف أبدأ؟', answer='شرح https://youtu.be/existing')
        response = self.upload(document(['1- كيف أبدأ؟', 'إجابة جديدة']))
        self.assertContains(response, 'https://youtu.be/existing')
        self.assertContains(response, 'الإجابة الجديدة لا تحتوي')

    def test_import_button_is_visible_in_question_list(self):
        self.assertContains(self.client.get(reverse('admin:accounts_supportquestion_changelist')), self.url)
