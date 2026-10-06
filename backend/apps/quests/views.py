"""
Views and API ViewSets for Quest creation and spatial querying.
"""

from django.db.models import Count, Q
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Quest
from .serializers import QuestSerializer, QuestGeoSerializer


class QuestViewSet(viewsets.ModelViewSet):
    """
    API endpoint for viewing and creating quests.
    Supports filtering by event ID and GeoJSON representation.
    """
    queryset = Quest.objects.all()
    serializer_class = QuestSerializer
    permission_classes = [permissions.AllowAny]

    def get_serializer_class(self):
        if self.request.query_params.get('format') == 'geojson':
            return QuestGeoSerializer
        return QuestSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        event_id = self.request.query_params.get('event')
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        return queryset

    def perform_update(self, serializer):
        """
        Saves the quest; when its value-scoring rule (validation_rules.scoring) changed, every
        team's points on it are settled again so bucket points and the bonus follow the new rule.
        """
        from apps.submissions.services.progress import recompute_quest

        before = (serializer.instance.validation_rules or {}).get('scoring')
        quest = serializer.save()
        if (quest.validation_rules or {}).get('scoring') != before:
            recompute_quest(quest)

    @action(detail=True, methods=['get'])
    def standings(self, request, pk=None):
        """
        Every team's standing on the quest, most points first: the points it holds from the
        quest, value-scoring buckets and best value, and how many verified submissions it has.
        For a quest with an extreme bonus, extreme_value is the current extreme and
        extreme_holder_team_ids the team(s) holding it (empty / null otherwise).
        """
        from apps.submissions.models import QuestProgress
        from apps.submissions.serializers import QuestStandingSerializer
        from apps.submissions.services.progress import quest_extreme

        quest = self.get_object()
        rows = (
            QuestProgress.objects.filter(quest=quest).select_related('team')
            .annotate(verified_count=Count(
                'team__submissions',
                filter=Q(team__submissions__quest=quest, team__submissions__is_verified=True),
            ))
            .filter(Q(verified_count__gt=0) | Q(awarded_points__gt=0))
            .order_by('-awarded_points', 'team__name')
        )
        extreme_value, holders = quest_extreme(quest)
        return Response({
            'quest': quest.id,
            'standings': QuestStandingSerializer(rows, many=True).data,
            'extreme_value': extreme_value,
            'extreme_holder_team_ids': holders,
        })
