"""
Submission and Multi-Platform Ingestion Models.
"""

from django.db import models
from apps.events.models import Event
from apps.quests.models import Quest


class Submission(models.Model):
    """
    Represents an open data contribution harvested from OpenStreetMap,
    Wikimedia Commons, or Wikidata matching the event hashtag.
    """
    PLATFORMS = [
        ('osm', 'OpenStreetMap'),
        ('commons', 'Wikimedia Commons'),
        ('wikidata', 'Wikidata'),
        ('ohm', 'OpenHistoricalMap'),
        ('osm_notes', 'OpenStreetMap Notes'),
        ('checkin', 'GPS Check-in'),
        ('github', 'GitHub'),
        ('panoramax', 'Panoramax'),
        ('mangrove', 'Mangrove Reviews'),
        ('maproulette', 'MapRoulette'),
    ]

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='submissions',
        help_text="The event this submission belongs to."
    )
    quest = models.ForeignKey(
        Quest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='submissions',
        help_text="Matched quest (if criteria tags match)."
    )
    team = models.ForeignKey(
        'teams.Team',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='submissions',
        help_text="Team credited with the submission (if author is a member)."
    )
    platform = models.CharField(
        max_length=16,
        choices=PLATFORMS,
        help_text="Source platform of the contribution."
    )
    external_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Changeset ID, Page ID, or Revision ID on the target platform."
    )
    author_username = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Username of the contributor on the external platform."
    )
    external_url = models.URLField(
        help_text="Direct link to the external changeset, photo, or item."
    )
    diff_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured diff showing added/modified tags, images, or statements."
    )
    is_verified = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether a host has reviewed and verified this submission."
    )
    verified_by_username = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Host username who confirmed verification."
    )
    verified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when verification was granted."
    )
    element_count = models.PositiveIntegerField(
        default=1,
        help_text=(
            "How many distinct contributions this submission represents toward a counted quest "
            "(e.g. 3 cafes given opening_hours in one changeset)."
        )
    )
    contributed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the contribution happened on the external platform (created_at is when it was harvested)."
    )
    extracted_value = models.FloatField(
        null=True,
        blank=True,
        help_text=(
            "Value read for a value-scoring quest (validation_rules.scoring), e.g. the year on a "
            "sidewalk stamp. For element-based submissions this is the extreme of the per-element "
            "values stored in diff_payload['extracted_values']. Hosts can correct it when verifying."
        )
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the submission was harvested."
    )

    class Meta:
        ordering = ['-created_at']
        unique_together = ('platform', 'external_id')
        verbose_name = 'Open Data Submission'
        verbose_name_plural = 'Open Data Submissions'

    def __str__(self):
        return f"[{self.get_platform_display()}] {self.external_id} by {self.author_username} ({'Verified' if self.is_verified else 'Pending'})"


class QuestProgress(models.Model):
    """
    A team's running tally toward one quest.

    Rows are derived data: services.progress.recompute_quest_progress rebuilds them from
    verified submissions, and records how many of the quest's points are currently included in
    the team score (awarded_points) so that awarding and revoking stay idempotent.
    """
    team = models.ForeignKey(
        'teams.Team',
        on_delete=models.CASCADE,
        related_name='quest_progress',
        help_text="Team whose progress this row tracks."
    )
    quest = models.ForeignKey(
        Quest,
        on_delete=models.CASCADE,
        related_name='team_progress',
        help_text="Quest being progressed."
    )
    count = models.PositiveIntegerField(
        default=0,
        help_text="Sum of element_count across the team's verified submissions for this quest."
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When count first reached the quest's target_count (cleared if it drops below)."
    )
    points_awarded = models.BooleanField(
        default=False,
        help_text="Whether quest.points_reward (the completion points) is currently included in team.score."
    )
    awarded_points = models.IntegerField(
        default=0,
        help_text=(
            "Points the team currently holds from this quest: completion points plus any value-scoring "
            "bucket points and extreme bonus. team.score moves by the change in this value."
        )
    )
    buckets = models.JSONField(
        default=list,
        blank=True,
        help_text="Value-scoring buckets found (bucket starts, e.g. [1920, 1950] for decades), sorted."
    )
    best_value = models.FloatField(
        null=True,
        blank=True,
        help_text="The team's extreme verified value on a value-scoring quest (min or max per the rule)."
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp of the last recompute."
    )

    class Meta:
        unique_together = ('team', 'quest')
        ordering = ['quest__title']
        verbose_name = 'Quest Progress'
        verbose_name_plural = 'Quest Progress'

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    def __str__(self):
        return f"{self.team.name}: {self.quest.title} ({self.count}/{self.quest.target_count})"


class TrackedOsmElement(models.Model):
    """
    What the harvester has learned about one OSM element for one `osm_tags` quest with
    `"action": "create"`.

    Overpass only returns an element's current version, so who created the element, and when,
    comes from its version 1: read from the Overpass result when the current version is 1, and
    otherwise from the OSM history API. Version 1 never changes, so it is stored here and the
    history API is only asked again when the element's version goes past last_seen_version.
    """
    ELEMENT_TYPES = [
        ('node', 'Node'),
        ('way', 'Way'),
        ('relation', 'Relation'),
    ]

    quest = models.ForeignKey(
        Quest,
        on_delete=models.CASCADE,
        related_name='tracked_osm_elements',
        help_text="Quest the element was matched for."
    )
    element_type = models.CharField(
        max_length=8,
        choices=ELEMENT_TYPES,
        help_text="OSM element type."
    )
    element_id = models.BigIntegerField(
        help_text="OSM element id."
    )
    last_seen_version = models.PositiveIntegerField(
        default=1,
        help_text="Highest element version seen by the harvester; a higher one triggers a new history lookup."
    )
    created_at_osm = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of version 1 (null when the history did not include it)."
    )
    creator_username = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="User who created the element (version 1)."
    )
    creation_changeset = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Changeset that created the element (version 1)."
    )
    last_editor_username = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="User who made the latest version seen."
    )
    last_checked = models.DateTimeField(
        auto_now=True,
        help_text="When the harvester last saw the element."
    )

    class Meta:
        unique_together = ('quest', 'element_type', 'element_id')
        verbose_name = 'Tracked OSM Element'
        verbose_name_plural = 'Tracked OSM Elements'

    def __str__(self):
        return f"{self.element_type}/{self.element_id} v{self.last_seen_version} for quest {self.quest_id}"
