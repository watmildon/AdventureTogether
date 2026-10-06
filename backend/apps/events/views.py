"""
Views and API ViewSets for Event management.
"""

from django.db.models import Count, Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.teams.serializers import TeamLeaderboardSerializer
from .models import Event
from .serializers import EventSerializer, EventGeoSerializer
from .services.schedule import ScheduleFetchError, fetch_schedule_sessions


class EventViewSet(viewsets.ModelViewSet):
    """
    API endpoint for listing, creating, and retrieving scavenger hunt events.
    Supports GeoJSON output via ?format=geojson or dedicated /geojson/ action.
    """
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [permissions.AllowAny]

    def get_serializer_class(self):
        if self.request.query_params.get('format') == 'geojson':
            return EventGeoSerializer
        return EventSerializer

    @action(detail=True, methods=['get'], serializer_class=EventGeoSerializer)
    def geojson(self, request, pk=None):
        """
        Returns the event and its bounding polygon formatted as a GeoJSON Feature.
        """
        event = self.get_object()
        serializer = EventGeoSerializer(event, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def leaderboard(self, request, pk=None):
        """
        Returns the event's teams ranked by score (ties broken by name), with roster size
        and the number of quests each team has completed.
        """
        event = self.get_object()
        teams = (
            event.teams
            .annotate(
                member_count=Count('memberships', distinct=True),
                completed_quests=Count(
                    'quest_progress',
                    filter=Q(quest_progress__completed_at__isnull=False),
                    distinct=True,
                ),
            )
            .order_by('-score', 'name')
        )
        return Response(TeamLeaderboardSerializer(teams, many=True).data)

    @action(detail=True, methods=['get'])
    def sessions(self, request, pk=None):
        """
        Returns the conference sessions from the event's schedule_url (pretalx/frab JSON),
        flattened into the Quest.inspired_by shape. Cached for 10 minutes per URL.
        """
        event = self.get_object()
        if not event.schedule_url:
            return Response(
                {'error': 'This event has no schedule_url configured.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            sessions = fetch_schedule_sessions(event.schedule_url)
        except ScheduleFetchError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(sessions)
