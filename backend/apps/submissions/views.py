"""
Views and API ViewSets for Ingested Submissions, Host Verification, and Harvesting.
"""

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Submission
from .serializers import SubmissionSerializer, VerifySubmissionInputSerializer
from .services.harvest_worker import harvest_event_submissions
from .services.progress import set_submission_verification


class SubmissionViewSet(viewsets.ModelViewSet):
    """
    API endpoint for listing ingested submissions and verifying changesets.
    """
    queryset = Submission.objects.all()
    serializer_class = SubmissionSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()
        event_id = self.request.query_params.get('event')
        is_verified = self.request.query_params.get('is_verified')
        quest_id = self.request.query_params.get('quest')

        if event_id:
            queryset = queryset.filter(event_id=event_id)
        if is_verified is not None:
            queryset = queryset.filter(is_verified=is_verified.lower() in ('true', '1'))
        if quest_id:
            queryset = queryset.filter(quest_id=quest_id)

        return queryset

    @action(detail=True, methods=['post'], serializer_class=VerifySubmissionInputSerializer)
    def verify(self, request, pk=None):
        """
        Host action to verify a submission diff and award quest points to the team.
        """
        submission = self.get_object()
        serializer = VerifySubmissionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        is_verified = serializer.validated_data.get('is_verified', True)
        verified_by = serializer.validated_data.get('verified_by_username', 'Host')

        # Scoring lives in the progress service so counted quests (target_count > 1)
        # award points only once the team reaches the target, and revoke idempotently.
        set_submission_verification(submission, is_verified, verified_by)

        return Response(
            SubmissionSerializer(submission).data,
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['post'])
    def trigger_harvest(self, request):
        """
        Manually triggers a harvest cycle for a given event.
        """
        event_id = request.data.get('event') or request.query_params.get('event')
        if not event_id:
            return Response(
                {'error': 'Field "event" is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        stats = harvest_event_submissions(int(event_id))
        return Response({
            'message': f'Harvest completed for event {event_id}.',
            'stats': stats
        }, status=status.HTTP_200_OK)
