"""
Quest progress and scoring.

A team's score is derived from QuestProgress rows: a quest's points are added once when the
team's verified contributions reach the quest's target_count, and removed again if a host
revokes enough of them to drop back below the target. Keeping the "points awarded" flag on
the progress row makes recomputation idempotent, so it is safe to call after any change to a
submission's verification, team, quest, or element_count.
"""

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.quests.models import Quest
from apps.teams.models import Team
from apps.submissions.models import QuestProgress, Submission


def recompute_quest_progress(team: Team, quest: Quest) -> QuestProgress:
    """
    Rebuilds the team's progress on a quest from its verified submissions and settles the
    team score: awards quest.points_reward on completion and revokes it (flooring the score
    at 0) if the team falls back below the target.
    """
    with transaction.atomic():
        # Lock the team row so concurrent verifications cannot double-award or lose an update.
        locked_team = Team.objects.select_for_update().get(pk=team.pk)

        progress, _ = QuestProgress.objects.get_or_create(team=locked_team, quest=quest)

        total = Submission.objects.filter(
            team=locked_team, quest=quest, is_verified=True
        ).aggregate(total=Sum('element_count'))['total'] or 0

        progress.count = total
        is_complete = total >= quest.target_count

        if is_complete:
            if progress.completed_at is None:
                progress.completed_at = timezone.now()
            if not progress.points_awarded:
                locked_team.score += quest.points_reward
                locked_team.save(update_fields=['score'])
                progress.points_awarded = True
        else:
            progress.completed_at = None
            if progress.points_awarded:
                locked_team.score = max(0, locked_team.score - quest.points_reward)
                locked_team.save(update_fields=['score'])
                progress.points_awarded = False

        progress.save()

    # Keep the caller's in-memory team in step with the database.
    team.score = locked_team.score
    return progress


def set_submission_verification(submission: Submission, is_verified: bool, by: str = 'Host') -> Submission:
    """
    Verifies (or un-verifies) a submission and recomputes the affected team's quest progress.
    """
    with transaction.atomic():
        submission.is_verified = is_verified
        submission.verified_by_username = by if is_verified else None
        submission.verified_at = timezone.now() if is_verified else None
        submission.save(update_fields=['is_verified', 'verified_by_username', 'verified_at'])

        if submission.team_id and submission.quest_id:
            recompute_quest_progress(submission.team, submission.quest)

    return submission


def mark_verified(submission: Submission, by: str = 'system') -> Submission:
    """
    Convenience for code paths that create already-verified submissions (e.g. automatic GPS
    check-ins): marks the submission verified and settles progress and score.
    """
    return set_submission_verification(submission, True, by)
