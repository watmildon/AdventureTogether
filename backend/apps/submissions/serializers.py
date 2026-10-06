"""
Serializers for Ingested Submissions and Host Verification.
"""

from rest_framework import serializers
from .models import QuestProgress, Submission


class SubmissionSerializer(serializers.ModelSerializer):
    """
    Serializer for Submission objects with embedded quest and team details.
    """
    quest_title = serializers.CharField(source='quest.title', read_only=True, allow_null=True)
    team_name = serializers.CharField(source='team.name', read_only=True, allow_null=True)
    platform_display = serializers.CharField(source='get_platform_display', read_only=True)

    class Meta:
        model = Submission
        fields = [
            'id',
            'event',
            'quest',
            'quest_title',
            'team',
            'team_name',
            'platform',
            'platform_display',
            'external_id',
            'author_username',
            'external_url',
            'diff_payload',
            'is_verified',
            'verified_by_username',
            'verified_at',
            'element_count',
            'contributed_at',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class VerifySubmissionInputSerializer(serializers.Serializer):
    """
    Input serializer for verifying or un-verifying a staged submission.
    """
    is_verified = serializers.BooleanField(default=True)
    verified_by_username = serializers.CharField(max_length=255, default='Host')


class QuestProgressSerializer(serializers.ModelSerializer):
    """
    A team's progress on one quest. Also used for unsaved placeholder rows (count 0) so
    clients can render every quest of the event, not only those already started.
    """
    quest_title = serializers.CharField(source='quest.title', read_only=True)
    target_count = serializers.IntegerField(source='quest.target_count', read_only=True)
    points_reward = serializers.IntegerField(source='quest.points_reward', read_only=True)

    class Meta:
        model = QuestProgress
        fields = [
            'quest',
            'quest_title',
            'count',
            'target_count',
            'points_reward',
            'completed_at',
            'points_awarded',
        ]
        read_only_fields = fields
