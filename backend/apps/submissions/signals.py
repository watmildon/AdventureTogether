"""
Signal receivers that keep team scores consistent with QuestProgress.

QuestProgress rows cascade when their quest is deleted (QuestViewSet.destroy, seed_event
--replace-quests, the admin), so the points those rows had added to team.score (awarded_points:
completion points plus any value-scoring bucket points and bonus) would otherwise stay on the
leaderboard with nothing left to revoke them.
"""

from django.db import transaction
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from apps.quests.models import Quest
from apps.teams.models import Team
from apps.submissions.models import QuestProgress


@receiver(pre_delete, sender=Quest, dispatch_uid='submissions.revoke_points_on_quest_delete')
def revoke_points_on_quest_delete(sender, instance: Quest, **kwargs):
    """
    Subtracts the points each team holds from the quest (its progress row's awarded_points,
    flooring the score at 0) before the quest and its QuestProgress rows are deleted.
    """
    with transaction.atomic():
        held = {}
        for team_id, awarded, completed in QuestProgress.objects.filter(quest=instance).values_list(
                'team_id', 'awarded_points', 'points_awarded'):
            # A row written before awarded_points existed only has the completion flag.
            points = awarded or (instance.points_reward if completed else 0)
            if points > 0:
                held[team_id] = points
        if not held:
            return
        # Lock the teams as recompute_quest_progress does, so a concurrent award cannot be lost.
        for team in Team.objects.select_for_update().filter(pk__in=held).order_by('pk'):
            team.score = max(0, team.score - held[team.pk])
            team.save(update_fields=['score'])
