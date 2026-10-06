"""
Serializers for Quest models and spatial validation.
"""

from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import Quest


class QuestSerializer(serializers.ModelSerializer):
    """
    Standard serializer for Quests with spatial containment validation.
    """
    # Derived from validation_rules['target_count']; read-only so there is one source of truth.
    target_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Quest
        fields = [
            'id',
            'event',
            'title',
            'description',
            'target_geometry',
            'criteria_type',
            'validation_rules',
            'points_reward',
            'is_active',
            'inspired_by',
            'window_start',
            'window_end',
            'target_count',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_inspired_by(self, value):
        """
        inspired_by must be a JSON object (possibly empty); its keys are documented on Quest.inspired_by.
        """
        if not isinstance(value, dict):
            raise serializers.ValidationError('inspired_by must be a JSON object, e.g. {"title": "...", "url": "..."}.')
        return value

    def validate_validation_rules(self, value):
        """
        The optional value-scoring block (validation_rules.scoring) must be well formed; other
        keys are type-specific and checked where they are used.
        """
        from apps.submissions.services.value_extraction import validate_scoring

        if isinstance(value, dict):
            errors = validate_scoring(value.get('scoring'))
            if errors:
                raise serializers.ValidationError(errors)
        return value

    def validate(self, attrs):
        """
        Validates that quest target geometry resides within or intersects the event bounding perimeter,
        and that an optional quest time window is not inverted.
        """
        window_start = attrs.get('window_start', getattr(self.instance, 'window_start', None))
        window_end = attrs.get('window_end', getattr(self.instance, 'window_end', None))
        if window_start and window_end and window_start > window_end:
            raise serializers.ValidationError({
                'window_end': 'Quest window_end must be on or after window_start.'
            })

        event = attrs.get('event') or (self.instance.event if self.instance else None)
        target_geometry = attrs.get('target_geometry', getattr(self.instance, 'target_geometry', None))

        if event and target_geometry:
            if not event.is_within_bounds(target_geometry):
                raise serializers.ValidationError({
                    'target_geometry': 'Quest target geometry must reside within or intersect the event bounding perimeter.'
                })
        return attrs


class QuestGeoSerializer(GeoFeatureModelSerializer):
    """
    GeoJSON Feature serializer for Quests.
    """
    target_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Quest
        geo_field = 'target_geometry'
        fields = [
            'id',
            'event',
            'title',
            'description',
            'criteria_type',
            'validation_rules',
            'points_reward',
            'is_active',
            'inspired_by',
            'window_start',
            'window_end',
            'target_count',
            'created_at',
        ]
