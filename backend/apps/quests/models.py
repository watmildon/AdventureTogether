"""
Quest and Geospatial Challenge Models.
"""

from django.contrib.gis.db import models as gis_models
from django.db import models
from apps.events.models import Event


class Quest(models.Model):
    """
    Represents a scavenger hunt challenge created by a host.
    Includes target geometries (points or zones) and open data validation criteria.
    """
    CRITERIA_TYPES = [
        ('osm_tags', 'OpenStreetMap Tag Rule'),
        ('wikimedia_commons', 'Wikimedia Commons Photo'),
        ('wikidata_entry', 'Wikidata Item Edit'),
        ('location_checkin', 'GPS Check-in'),
        ('osm_notes', 'OpenStreetMap Note Resolved'),
        ('ohm_feature', 'OpenHistoricalMap Feature'),
        ('wikidata_statement', 'Wikidata Statement on Item'),
        ('oss_contribution', 'Open Source Contribution (GitHub)'),
        ('street_imagery', 'Street-level Imagery (Panoramax)'),
        ('mangrove_review', 'Mangrove Place Review'),
        ('maproulette_task', 'MapRoulette Task Fixed'),
    ]

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='quests',
        help_text="The event this quest belongs to."
    )
    title = models.CharField(
        max_length=255,
        help_text="Short title of the quest challenge."
    )
    description = models.TextField(
        help_text="Instructions for field participants."
    )
    target_geometry = gis_models.GeometryField(
        srid=4326,
        null=True,
        blank=True,
        help_text="Specific point, polygon zone, or geometry for the quest (optional, defaults to entire event perimeter)."
    )
    criteria_type = models.CharField(
        max_length=32,
        choices=CRITERIA_TYPES,
        default='osm_tags',
        help_text="Platform and verification type for this quest."
    )
    validation_rules = models.JSONField(
        default=dict,
        blank=True,
        help_text='JSON criteria: e.g. {"required_tags": {"amenity": "restaurant", "opening_hours": "*"}, "target_count": 5}'
    )
    points_reward = models.IntegerField(
        default=10,
        help_text="Score awarded to a team upon verified completion."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this quest is active for completion."
    )
    inspired_by = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Conference session that inspired this quest (empty when none). Shape: '
            '{"code": "ABC123", "title": "Talk title", "speakers": ["Name"], '
            '"start": "2026-11-03T16:00:00-08:00", "room": "Room name", "track": "Track name", '
            '"url": "https://talks.example.org/talk/ABC123/"}'
        )
    )
    window_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional start of a quest-specific time window inside the event window (e.g. Monday evening only)."
    )
    window_end = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional end of a quest-specific time window inside the event window."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the quest was created."
    )

    class Meta:
        ordering = ['title']
        verbose_name = 'Scavenger Hunt Quest'
        verbose_name_plural = 'Scavenger Hunt Quests'

    @property
    def target_count(self) -> int:
        """
        Number of distinct contributions a team needs before this quest counts as complete.
        Read from validation_rules['target_count']; missing or invalid values fall back to 1.
        """
        try:
            count = int(self.validation_rules.get('target_count', 1))
        except (TypeError, ValueError, AttributeError):
            return 1
        return max(1, count)

    def is_open_at(self, dt) -> bool:
        """
        Whether contributions made at `dt` can count toward this quest.
        An inactive quest is never open; otherwise the optional quest window applies
        (each bound is inclusive and only enforced when set).
        """
        if not self.is_active:
            return False
        if self.window_start and dt < self.window_start:
            return False
        if self.window_end and dt > self.window_end:
            return False
        return True

    def __str__(self):
        return f"{self.title} ({self.get_criteria_type_display()}) - Event: {self.event.title}"
