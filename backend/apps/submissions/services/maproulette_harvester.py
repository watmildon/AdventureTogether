"""
MapRoulette harvester (`maproulette_task` quests).

MapRoulette (https://maproulette.org) serves "challenges": lists of small OSM fixes, one task
per spot. `GET {MAPROULETTE_API}/tasks/box/{left}/{bottom}/{right}/{top}` lists the tasks in a
bounding box, 200 a page. The listing only includes tasks in the statuses passed as `tStatus`
(without it, fixed tasks are left out), and its `modified` is the time of the response rather
than of the task, so the window is judged from `mappedOn` instead.

A task counts when its status is one the quest accepts (fixed or already fixed by default), it
was mapped during the window, it lies in the quest's area and, when the quest names challenges,
it belongs to one of them. Each such task is fetched once (`GET /task/{id}`, counted in the
`detail_lookups` stat) to learn its OSM changeset; a task whose stored submission shows the same
status and mapping time is not fetched again.

Credit goes to the OSM user: from the changeset's metadata when MapRoulette recorded one
(which is also the only way to check the hashtag), else from the MapRoulette user who completed
the task (MapRoulette accounts are OSM logins, so their public profile carries the OSM name).
"""

from typing import Any, Dict, List, Optional

from django.conf import settings

from apps.quests.models import Quest
from apps.submissions.models import Submission
from .harvest_common import (
    HarvestContext,
    HarvestError,
    counts_for_quest,
    http_get,
    parse_timestamp,
    point_in_quest_area,
    quest_bbox,
    union_bbox,
    upsert_submission,
)
from .overpass_harvester import OSM, fetch_changeset_meta
from .tag_matcher import hashtag_matches

PLATFORM = 'maproulette'
MAPROULETTE_HTTP_TIMEOUT = 30
PAGE_LIMIT = 200
MAX_PAGES = 20
# Task statuses: 0 created, 1 fixed, 2 false positive, 3 skipped, 4 deleted, 5 already fixed,
# 6 too hard. A quest credits fixed and already-fixed tasks unless it says otherwise.
DEFAULT_STATUSES = (1, 5)
TASK_URL = 'https://maproulette.org/challenge/{challenge}/task/{task}'


def _int_list(value: Any) -> List[int]:
    items = value if isinstance(value, (list, tuple)) else str(value or '').replace(',', ' ').split()
    result = []
    for item in items:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def quest_statuses(quest: Quest) -> List[int]:
    statuses = _int_list((quest.validation_rules or {}).get('statuses'))
    return statuses or list(DEFAULT_STATUSES)


def quest_challenges(quest: Quest) -> List[int]:
    return _int_list((quest.validation_rules or {}).get('challenge_ids'))


def fetch_tasks_in_box(ctx: HarvestContext, bbox, statuses: List[int]) -> List[Dict[str, Any]]:
    """
    Every task in a (min_lon, min_lat, max_lon, max_lat) box with one of the statuses, paging
    while pages come back full, up to MAX_PAGES pages (a warning is recorded when the cap is hit).
    """
    left, bottom, right, top = bbox
    base = settings.MAPROULETTE_API.rstrip('/')
    url = f'{base}/tasks/box/{left:.6f}/{bottom:.6f}/{right:.6f}/{top:.6f}'
    tasks: List[Dict[str, Any]] = []
    for page in range(MAX_PAGES):
        data = http_get(
            url,
            'MapRoulette tasks',
            params={'limit': PAGE_LIMIT, 'page': page, 'tStatus': ','.join(str(s) for s in statuses)},
            timeout=MAPROULETTE_HTTP_TIMEOUT,
        )
        items = data if isinstance(data, list) else (data or {}).get('tasks') or []
        tasks.extend(item for item in items if isinstance(item, dict))
        if len(items) < PAGE_LIMIT:
            return tasks
    ctx.warnings.append(f'MapRoulette task listing stopped at {MAX_PAGES} pages; narrow the quest area')
    return tasks


def fetch_task(ctx: HarvestContext, task_id: int) -> Dict[str, Any]:
    """The full task (completedBy, mappedOn, changesetId, ...), fetched at most once per run."""
    key = ('maproulette-task', task_id)
    if key not in ctx.cache:
        ctx.platform(PLATFORM)['detail_lookups'] += 1
        base = settings.MAPROULETTE_API.rstrip('/')
        ctx.cache[key] = http_get(f'{base}/task/{int(task_id)}', 'MapRoulette task',
                                  timeout=MAPROULETTE_HTTP_TIMEOUT)
    return ctx.cache[key]


def fetch_user_osm_name(ctx: HarvestContext, user_id: int) -> str:
    """
    The OSM display name of a MapRoulette user, from `GET /user/{id}/public`
    (`osmProfile.displayName`, falling back to `name`). '' when unknown. Cached for the run.
    """
    key = ('maproulette-user', user_id)
    if key not in ctx.cache:
        base = settings.MAPROULETTE_API.rstrip('/')
        data = http_get(f'{base}/user/{int(user_id)}/public', 'MapRoulette user',
                        timeout=MAPROULETTE_HTTP_TIMEOUT)
        profile = (data or {}).get('osmProfile') or {}
        ctx.cache[key] = str(profile.get('displayName') or (data or {}).get('name') or '')
    return ctx.cache[key]


def _completed_by(item: Dict[str, Any], task: Dict[str, Any]) -> tuple:
    """(MapRoulette user id, username) from the task (an id) or the listing ({id, username})."""
    listed = item.get('completedBy')
    user_id = task.get('completedBy')
    username = ''
    if isinstance(listed, dict):
        user_id = user_id if user_id is not None else listed.get('id')
        username = str(listed.get('username') or '')
    elif user_id is None:
        user_id = listed
    try:
        user_id = int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        user_id = None
    return user_id, username


def attribute_task(ctx: HarvestContext, item: Dict[str, Any], task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Who fixed the task: {author, attributed_by, changeset_id, has_hashtag, completed_by}.
    attributed_by is 'changeset' (OSM changeset metadata), 'completed_by' (the OSM name of the
    MapRoulette user who completed it, from the listing or their public profile) or 'user_id'
    (only the MapRoulette user id is known). has_hashtag is None when
    there is no changeset to check. Returns None when nobody can be credited.
    """
    try:
        changeset_id = int(task.get('changesetId') or -1)
    except (TypeError, ValueError):
        changeset_id = -1
    user_id, username = _completed_by(item, task)

    if changeset_id > 0:
        meta = fetch_changeset_meta(ctx, OSM, changeset_id)
        return {
            'author': meta['user'],
            'attributed_by': 'changeset',
            'changeset_id': changeset_id,
            'has_hashtag': hashtag_matches(meta['tags'], ctx.event.hashtag),
            'completed_by': user_id,
        }
    if user_id is None:
        return None
    if not username:
        username = fetch_user_osm_name(ctx, user_id)
    return {
        'author': username or f'MapRoulette user {user_id}',
        'attributed_by': 'completed_by' if username else 'user_id',
        'changeset_id': None,
        'has_hashtag': None,
        'completed_by': user_id,
    }


def _same_instant(a: Any, b: Any) -> bool:
    return parse_timestamp(a) == parse_timestamp(b)


def stored_is_current(submission: Optional[Submission], item: Dict[str, Any]) -> bool:
    """
    Whether a stored submission already reflects the listed task: same status, and the same
    mappedOn (or, when the listing has none, the same modified).
    """
    if submission is None:
        return False
    stored = submission.diff_payload or {}
    if stored.get('status') != item.get('status'):
        return False
    if item.get('mappedOn'):
        return _same_instant(stored.get('mapped_on'), item.get('mappedOn'))
    return _same_instant(stored.get('modified'), item.get('modified'))


def listed_task_matches(ctx: HarvestContext, quest: Quest, item: Dict[str, Any]) -> bool:
    """Status, challenge, area and (when the listing has mappedOn) window checks on a listed task."""
    if item.get('status') not in quest_statuses(quest):
        return False
    challenges = quest_challenges(quest)
    if challenges and item.get('parentId') not in challenges:
        return False
    point = item.get('point') or {}
    try:
        lat, lon = float(point['lat']), float(point['lng'])
    except (KeyError, TypeError, ValueError):
        return False
    if not point_in_quest_area(ctx.event, quest, lat, lon):
        return False
    mapped = parse_timestamp(item.get('mappedOn'))
    return mapped is None or counts_for_quest(ctx.event, quest, mapped)


def _upsert_stored(ctx: HarvestContext, quest: Quest, submission: Submission) -> None:
    """Re-offers a stored, unchanged task so a member who added their username later is credited."""
    upsert_submission(
        ctx,
        platform=PLATFORM,
        quest=quest,
        external_id=submission.external_id,
        external_url=submission.external_url,
        author_username=submission.author_username,
        contributed_at=submission.contributed_at,
        element_count=1,
        diff_payload=submission.diff_payload,
    )


def harvest_maproulette(ctx: HarvestContext, quests: List[Quest]) -> None:
    event = ctx.event
    # Per-task detail requests, so hosts can see the load on MapRoulette.
    ctx.platform(PLATFORM).setdefault('detail_lookups', 0)
    statuses = sorted({s for quest in quests for s in quest_statuses(quest)})
    bbox = union_bbox(quest_bbox(event, quest) for quest in quests)
    if bbox is None:
        return
    try:
        items = fetch_tasks_in_box(ctx, bbox, statuses)
    except HarvestError as exc:
        ctx.error(PLATFORM, str(exc))
        return

    stored = {s.external_id: s for s in Submission.objects.filter(platform=PLATFORM, quest__in=quests)}

    for item in items:
        task_id = item.get('id')
        if task_id is None:
            continue
        pending = []
        for quest in quests:
            if not listed_task_matches(ctx, quest, item):
                continue
            submission = stored.get(f'{task_id}/q{quest.id}')
            if stored_is_current(submission, item):
                _upsert_stored(ctx, quest, submission)
            else:
                pending.append(quest)
        if not pending:
            continue

        try:
            task = fetch_task(ctx, task_id)
            attribution = attribute_task(ctx, item, task)
        except HarvestError as exc:
            ctx.error(PLATFORM, f'task {task_id}: {exc}')
            continue
        if attribution is None:
            continue

        status = task.get('status', item.get('status'))
        mapped_on = task.get('mappedOn') or item.get('mappedOn')
        contributed_at = parse_timestamp(mapped_on) or parse_timestamp(task.get('modified'))
        challenge_id = task.get('parent') or item.get('parentId')
        for quest in pending:
            rules = quest.validation_rules or {}
            if status not in quest_statuses(quest):
                continue
            if not counts_for_quest(event, quest, contributed_at):
                continue
            # The hashtag can only be checked on a changeset; without one the task cannot count.
            if rules.get('require_hashtag', False) is True and not attribution['has_hashtag']:
                continue
            upsert_submission(
                ctx,
                platform=PLATFORM,
                quest=quest,
                external_id=f'{task_id}/q{quest.id}',
                external_url=TASK_URL.format(challenge=challenge_id, task=task_id),
                author_username=attribution['author'],
                contributed_at=contributed_at,
                element_count=1,
                diff_payload={
                    'challenge_id': challenge_id,
                    'challenge_name': item.get('parentName') or '',
                    'task_title': item.get('title') or task.get('name') or '',
                    'status': status,
                    'changeset_id': attribution['changeset_id'],
                    'mapped_on': mapped_on,
                    'modified': task.get('modified'),
                    'completed_by': attribution['completed_by'],
                    'attributed_by': attribution['attributed_by'],
                },
            )
