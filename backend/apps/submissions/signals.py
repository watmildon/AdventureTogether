"""
Signal receivers that keep team scores consistent with QuestProgress.

QuestProgress rows cascade when their quest is deleted (QuestViewSet.destroy, seed_event
--replace-quests, the admin), so the points those rows had added to team.score would otherwise
stay on the leaderboard with nothing left to revoke them.
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
    Subtracts the quest's points_reward from every team that was awarded it (flooring the score
    at 0) before the quest and its QuestProgress rows are deleted.
    """
    if not instance.points_reward:
        return

    with transaction.atomic():
        team_ids = list(
            QuestProgress.objects.filter(quest=instance, points_awarded=True).values_list('team_id', flat=True)
        )
        if not team_ids:
            return
        # Lock the teams as recompute_quest_progress does, so a concurrent award cannot be lost.
        for team in Team.objects.select_for_update().filter(pk__in=team_ids).order_by('pk'):
            team.score = max(0, team.score - instance.points_reward)
            team.save(update_fields=['score'])
