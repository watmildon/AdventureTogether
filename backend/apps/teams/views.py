"""
Views and API ViewSets for Team management and joining.
"""

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.submissions.models import QuestProgress
from apps.submissions.serializers import QuestProgressSerializer
from .models import Team, TeamMembership
from .serializers import TeamSerializer, TeamMembershipSerializer, JoinTeamRequestSerializer


class TeamViewSet(viewsets.ModelViewSet):
    """
    API endpoint for creating teams, viewing team rosters, and joining groups via join code.
    """
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()
        event_id = self.request.query_params.get('event')
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        return queryset

    @action(detail=False, methods=['post'], serializer_class=JoinTeamRequestSerializer)
    def join(self, request):
        """
        Allows a participant to join a team using a unique join code.
        """
        serializer = JoinTeamRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        join_code = serializer.validated_data['join_code'].strip().upper()
        user_identifier = serializer.validated_data['user_identifier'].strip()
        display_name = serializer.validated_data.get('display_name', 'Anonymous Mapper').strip()

        try:
            team = Team.objects.get(join_code__iexact=join_code)
        except Team.DoesNotExist:
            return Response(
                {'error': f'Team with join code "{join_code}" does not exist.'},
                status=status.HTTP_404_NOT_FOUND
            )

        defaults = {'display_name': display_name}
        # Only overwrite platform usernames the client actually sent, so re-joining from a
        # client that does not know about them does not wipe values entered earlier.
        for field in JoinTeamRequestSerializer.USERNAME_FIELDS:
            if field in serializer.validated_data:
                defaults[field] = serializer.validated_data[field].strip().lstrip('@')

        membership, created = TeamMembership.objects.update_or_create(
            team=team,
            user_identifier=user_identifier,
            defaults=defaults
        )

        return Response({
            'message': f'Successfully joined team {team.name}!',
            'team': TeamSerializer(team).data,
            'membership': TeamMembershipSerializer(membership).data
        }, status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def progress(self, request, pk=None):
        """
        Lists the team's progress on every quest of its event. Quests the team has not
        started yet appear with count 0 (unsaved placeholder rows; nothing is written).
        """
        team = self.get_object()
        existing = {
            p.quest_id: p
            for p in QuestProgress.objects.filter(team=team).select_related('quest')
        }
        rows = [
            existing.get(quest.id) or QuestProgress(team=team, quest=quest)
            for quest in team.event.quests.order_by('title', 'id')
        ]
        return Response(QuestProgressSerializer(rows, many=True).data)
