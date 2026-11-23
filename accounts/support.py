from .models import SupportQuestion
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


def support_questions_payload():
    # Full snapshot, independent of store cursors, also propagates removals.
    return list(SupportQuestion.objects.filter(is_active=True).values(
        'id', 'question', 'answer'))


@api_view(['GET'])
@permission_classes([AllowAny])
def support_questions_pull(request):
    response = Response({'support_questions': support_questions_payload()})
    response['Cache-Control'] = 'no-store'
    return response
