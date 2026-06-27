from django.urls import path
from .views import SubmitAssessmentView, AssessmentStatusView, SpellCheckView, RefundAssessmentView

urlpatterns = [
    path('submit/', SubmitAssessmentView.as_view(), name='submit_assessment'),
    path('status/<str:task_id>/', AssessmentStatusView.as_view(), name='assessment_status'),
    path('spellcheck/', SpellCheckView.as_view(), name='spellcheck'),
    path('refund/', RefundAssessmentView.as_view(), name='refund_assessment'),
]
