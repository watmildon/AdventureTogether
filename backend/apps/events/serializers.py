"""
Serializers for Event models.
"""

from rest_framework import serializers
from rest_framework_gis.serializers import GeoFeatureModelSerializer
from .models import Event


class EventSerializer(serializers.ModelSerializer):
    """
    Standard serializer for Event objects including GeoJSON bounding polygon.
    """
    class Meta:
        model = Event
        fields = [
            'id',
            'title',
            'slug',
            'description',
            'hashtag',
            'bounding_polygon',
            'start_time',
            'end_time',
            'schedule_url',
            'is_active',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {
            # The model generates a slug from the title on save, so clients may omit it.
            'slug': {'required': False, 'allow_blank': True},
        }

    def validate(self, attrs):
        """
        Drops a blank slug so Event.save() generates one from the title.
        """
        if 'slug' in attrs and not attrs['slug']:
            attrs.pop('slug')
        return attrs


class EventGeoSerializer(GeoFeatureModelSerializer):
    """
    GeoJSON-specific serializer representing Events as Feature objects.
    """
    class Meta:
        model = Event
        geo_field = 'bounding_polygon'
        fields = [
            'id',
            'title',
            'slug',
            'description',
            'hashtag',
            'start_time',
            'end_time',
            'schedule_url',
            'is_active',
            'created_at',
        ]
