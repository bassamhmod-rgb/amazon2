from .models import SupportQuestion


def support_questions_payload():
    # Full snapshot, independent of store cursors, also propagates removals.
    return list(SupportQuestion.objects.filter(is_active=True).values(
        'id', 'question', 'answer'))
