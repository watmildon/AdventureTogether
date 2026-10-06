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
    verified submissions, and records whether the quest's points have been added to the
    team score so that awarding and revoking stay idempotent.
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
        help_text="Whether quest.points_reward is currently included in team.score."
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
