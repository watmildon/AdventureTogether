"""
Quest progress and scoring.

A team's score is derived from QuestProgress rows: a quest's points are added once when the
team's verified contributions reach the quest's target_count, and removed again if a host
revokes enough of them to drop back below the target. Value-scoring quests
(validation_rules.scoring, see services.value_extraction) add points per distinct bucket of
values a team has found and a bonus for the team(s) holding the extreme value.

The points a team currently holds from a quest are stored on its progress row
(awarded_points) and the team score moves by the difference, which makes recomputation
idempotent: it is safe to call after any change to a submission's verification, team, quest,
element_count, or extracted_value.
"""

from typing import Dict, List, Optional, Tuple

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.quests.models import Quest
from apps.teams.models import Team
from apps.submissions.models import QuestProgress, Submission
from .value_extraction import ScoringRule, override_value, scoring_rule, submission_values

_UNSET = object()


def quest_values_by_team(quest: Quest) -> Dict[int, List[float]]:
    """Every value of the quest's verified, team-credited submissions, keyed by team id."""
    values: Dict[int, List[float]] = {}
    submissions = Submission.objects.filter(
        quest=quest, is_verified=True, team__isnull=False, extracted_value__isnull=False,
    ).only('team_id', 'extracted_value', 'diff_payload')
    for submission in submissions:
        values.setdefault(submission.team_id, []).extend(submission_values(submission))
    return values


def quest_extreme(quest: Quest, rule: Optional[ScoringRule] = None) -> Tuple[Optional[float], List[int]]:
    """
    (extreme value, ids of the teams holding it) over the quest's verified submissions, for a
    quest with an extreme_bonus; (None, []) otherwise or when there is no value yet. Ties share.
    """
    rule = rule or scoring_rule(quest)
    if rule is None or not rule.has_bonus:
        return None, []
    by_team = quest_values_by_team(quest)
    extreme = rule.extreme(v for values in by_team.values() for v in values)
    if extreme is None:
        return None, []
    return extreme, sorted(team_id for team_id, values in by_team.items() if extreme in values)


def recompute_quest_progress(team: Team, quest: Quest, *, extreme=_UNSET) -> QuestProgress:
    """
    Rebuilds the team's progress on a quest from its verified submissions and settles the
    team score. The team holds quest.points_reward once complete, plus for a value-scoring
    quest per_bucket.points for each distinct bucket among its values and extreme_bonus.points
    when one of its values is the extreme. team.score moves by the change from the stored
    awarded_points (a drop floors the score at 0).

    The extreme bonus depends on the other teams too, so after a change on such a quest use
    recompute_quest (or recompute_after_change), which re-evaluates every team. `extreme` lets
    it pass in the (value, team ids) it has already computed.
    """
    rule = scoring_rule(quest)
    with transaction.atomic():
        # Lock the team row so concurrent verifications cannot double-award or lose an update.
        locked_team = Team.objects.select_for_update().get(pk=team.pk)

        progress, _ = QuestProgress.objects.get_or_create(team=locked_team, quest=quest)

        verified = Submission.objects.filter(team=locked_team, quest=quest, is_verified=True)
        total = verified.aggregate(total=Sum('element_count'))['total'] or 0

        progress.count = total
        is_complete = total >= quest.target_count
        if is_complete:
            if progress.completed_at is None:
                progress.completed_at = timezone.now()
        else:
            progress.completed_at = None
        # Kept for clients that predate awarded_points: "the completion points are held".
        progress.points_awarded = is_complete
        points = quest.points_reward if is_complete else 0

        if rule is not None:
            values = [v for sub in verified.exclude(extracted_value__isnull=True)
                      for v in submission_values(sub)]
            progress.best_value = rule.extreme(values)
            if rule.bucket_size:
                progress.buckets = sorted({rule.bucket(v) for v in values})
                points += rule.bucket_points * len(progress.buckets)
            else:
                progress.buckets = []
            if rule.has_bonus:
                extreme_value, holders = quest_extreme(quest, rule) if extreme is _UNSET else extreme
                if locked_team.pk in holders:
                    points += rule.bonus_points
        else:
            progress.best_value = None
            progress.buckets = []

        delta = points - progress.awarded_points
        if delta:
            locked_team.score = max(0, locked_team.score + delta)
            locked_team.save(update_fields=['score'])
        progress.awarded_points = points
        progress.save()

    # Keep the caller's in-memory team in step with the database.
    team.score = locked_team.score
    return progress


def recompute_quest(quest: Quest, also_team: Optional[Team] = None) -> None:
    """
    Recomputes every team with progress or verified submissions on the quest (and also_team),
    in one transaction, so a bonus that moves between teams is taken from one and given to the
    other together. Teams are locked in id order.
    """
    rule = scoring_rule(quest)
    with transaction.atomic():
        team_ids = set(QuestProgress.objects.filter(quest=quest).values_list('team_id', flat=True))
        team_ids |= set(Submission.objects.filter(quest=quest, is_verified=True, team__isnull=False)
                        .values_list('team_id', flat=True))
        if also_team is not None:
            team_ids.add(also_team.pk)
        extreme = quest_extreme(quest, rule)
        for team in Team.objects.filter(pk__in=team_ids).order_by('pk'):
            recompute_quest_progress(team, quest, extreme=extreme)
            if also_team is not None and team.pk == also_team.pk:
                also_team.score = team.score


def recompute_after_change(team: Team, quest: Quest) -> None:
    """
    What to recompute after one team's submissions on a quest changed: just that team, or
    every team when the quest has an extreme bonus that may have moved.
    """
    rule = scoring_rule(quest)
    if rule is not None and rule.has_bonus:
        recompute_quest(quest, also_team=team)
    else:
        recompute_quest_progress(team, quest)


def set_submission_verification(submission: Submission, is_verified: bool, by: str = 'Host',
                                extracted_value=_UNSET) -> Submission:
    """
    Verifies (or un-verifies) a submission and recomputes the affected quest progress. When
    extracted_value is given it replaces the harvested value (a host's correction; None clears).
    """
    with transaction.atomic():
        submission.is_verified = is_verified
        submission.verified_by_username = by if is_verified else None
        submission.verified_at = timezone.now() if is_verified else None
        fields = ['is_verified', 'verified_by_username', 'verified_at']
        if extracted_value is not _UNSET:
            override_value(submission, extracted_value, by)
            fields += ['extracted_value', 'diff_payload']
        submission.save(update_fields=fields)

        if submission.team_id and submission.quest_id:
            recompute_after_change(submission.team, submission.quest)

    return submission


def mark_verified(submission: Submission, by: str = 'system') -> Submission:
    """
    Convenience for code paths that create already-verified submissions (e.g. automatic GPS
    check-ins): marks the submission verified and settles progress and score.
    """
    return set_submission_verification(submission, True, by)
