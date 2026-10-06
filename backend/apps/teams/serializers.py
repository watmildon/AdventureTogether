"""
Serializers for Team and Membership models.
"""

from rest_framework import serializers
from .models import Team, TeamMembership


class TeamMembershipSerializer(serializers.ModelSerializer):
    """
    Serializer for team participant memberships.
    """
    class Meta:
        model = TeamMembership
        fields = [
            'id',
            'user_identifier',
            'display_name',
            'osm_username',
            'wikimedia_username',
            'github_username',
            'joined_at',
        ]
        read_only_fields = ['id', 'joined_at']


class TeamSerializer(serializers.ModelSerializer):
    """
    Serializer for Teams with embedded member count and roster.
    """
    memberships = TeamMembershipSerializer(many=True, read_only=True)
    member_count = serializers.IntegerField(source='memberships.count', read_only=True)

    class Meta:
        model = Team
        fields = [
            'id',
            'event',
            'name',
            'join_code',
            'score',
            'member_count',
            'memberships',
            'created_at',
        ]
        read_only_fields = ['id', 'join_code', 'score', 'created_at']


class TeamLeaderboardSerializer(serializers.ModelSerializer):
    """
    One leaderboard row. Expects a queryset annotated with member_count and completed_quests
    (see EventViewSet.leaderboard).
    """
    member_count = serializers.IntegerField(read_only=True)
    completed_quests = serializers.IntegerField(read_only=True)

    class Meta:
        model = Team
        fields = ['id', 'name', 'score', 'member_count', 'completed_quests']
        read_only_fields = fields


class JoinTeamRequestSerializer(serializers.Serializer):
    """
    Input serializer for joining a team via join code.
    """
    join_code = serializers.CharField(max_length=32, required=True)
    user_identifier = serializers.CharField(max_length=255, required=True)
    display_name = serializers.CharField(max_length=255, required=False, default='Anonymous Mapper')
    # Optional external accounts so harvested edits can be credited to the team.
    # Omitted fields leave any previously stored value untouched on re-join.
    osm_username = serializers.CharField(max_length=255, required=False, allow_blank=True)
    wikimedia_username = serializers.CharField(max_length=255, required=False, allow_blank=True)
    github_username = serializers.CharField(max_length=255, required=False, allow_blank=True)

    USERNAME_FIELDS = ('osm_username', 'wikimedia_username', 'github_username')
