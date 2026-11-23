from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from stores.models import Store
from .models import SupportQuestion


class SupportQuestionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('supportadmin', password='test-only')
        self.store = Store.objects.create(owner=self.user, name='Support test', slug='support-test')
        self.second = SupportQuestion.objects.create(question='الثاني', answer='شرح https://youtu.be/example', sort_order=2)
        self.first = SupportQuestion.objects.create(question='الأول', answer='الإجابة', sort_order=1)
        SupportQuestion.objects.create(question='مخفي', answer='مسودة', is_active=False)

    def test_snapshot_in_both_sync_responses_including_empty_store_delta(self):
        for url in [
            '/api/mobile/v1/stores/?since=9223372036854775807',
            f'/api/mobile/v1/store-users/?merchant_id={self.store.pk}',
        ]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            questions = response.json()['support_questions']
            self.assertEqual([q['id'] for q in questions], [self.first.pk, self.second.pk])
            self.assertIn('https://youtu.be/example', questions[1]['answer'])

    def test_removal_propagates_as_empty_snapshot(self):
        SupportQuestion.objects.all().delete()
        self.assertEqual(self.client.get('/api/mobile/v1/stores/').json()['support_questions'], [])

    def test_dedicated_refresh_excludes_disabled_and_deleted_questions(self):
        url = '/api/mobile/v1/support-questions/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {'support_questions'})
        self.assertEqual([q['id'] for q in response.json()['support_questions']],
                         [self.first.pk, self.second.pk])
        self.first.is_active = False
        self.first.save()
        self.second.delete()
        self.assertEqual(self.client.get(url).json()['support_questions'], [])
        self.assertEqual(self.client.post(url).status_code, 405)

    def test_admin_management_and_access(self):
        url = reverse('admin:accounts_supportquestion_changelist')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse('admin:index')), url)
        self.assertContains(self.client.get(url), self.first.question)
        response = self.client.post(reverse('admin:accounts_supportquestion_add'), {
            'question': 'سؤال جديد', 'answer': 'https://www.youtube.com/watch?v=example',
            'sort_order': 3, 'is_active': 'on', '_save': 'Save',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(SupportQuestion.objects.filter(question='سؤال جديد').exists())
