"""
Team and Participant Membership Models.
"""

import secrets
import string
from django.db import models
from apps.events.models import Event


def generate_join_code(length: int = 6) -> str:
    """Generates a secure, human-readable alphanumeric join code (excluding ambiguous chars)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class Team(models.Model):
    """
    Represents a cooperative team participating in a scavenger hunt event.
    """
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='teams',
        help_text="The event this team is competing in."
    )
    name = models.CharField(
        max_length=255,
        help_text="Team name chosen by participants."
    )
    join_code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        default=generate_join_code,
        help_text="Unique code used by teammates to join this group."
    )
    score = models.IntegerField(
        default=0,
        help_text="Aggregate points earned by verified quest submissions."
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the team was created."
    )

    class Meta:
        ordering = ['-score', 'name']
        unique_together = ('event', 'name')
        verbose_name = 'Scavenger Hunt Team'
        verbose_name_plural = 'Scavenger Hunt Teams'

    def __str__(self):
        return f"{self.name} ({self.join_code}) - Event: {self.event.title}"


class TeamMembership(models.Model):
    """
    Represents an individual participant associated with a team.
    """
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='memberships',
        help_text="The team the user belongs to."
    )
    user_identifier = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Unique device identifier or username for the participant."
    )
    display_name = models.CharField(
        max_length=255,
        default='Anonymous Mapper',
        help_text="Participant display name visible to teammates."
    )
    # External platform accounts, used by the harvesters to credit contributions to this
    # member's team instead of guessing from display names. All optional.
    osm_username = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="OpenStreetMap (and OpenHistoricalMap) username, if the participant shared it."
    )
    wikimedia_username = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Wikimedia account name (Commons / Wikidata), if the participant shared it."
    )
    github_username = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="GitHub login, if the participant shared it."
    )
    joined_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the member joined the team."
    )

    class Meta:
        unique_together = ('team', 'user_identifier')
        ordering = ['joined_at']

    def __str__(self):
        return f"{self.display_name} in {self.team.name}"
