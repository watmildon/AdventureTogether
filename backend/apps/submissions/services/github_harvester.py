"""
GitHub harvester (`oss_contribution` quests).

Uses the GitHub issue search API to find pull requests and issues opened during the event with
the hashtag in their title or body. Set GITHUB_TOKEN in the environment: unauthenticated search
is limited to 10 requests a minute.
"""

import logging
from typing import Any, Dict, List

from django.conf import settings

from apps.quests.models import Quest
from .harvest_common import (
    HarvestContext,
    HarvestError,
    counts_for_quest,
    http_get,
    parse_timestamp,
    upsert_submission,
)
from .tag_matcher import hashtag_matches

logger = logging.getLogger('apps.submissions.harvest')

PLATFORM = 'github'
GITHUB_SEARCH_URL = 'https://api.github.com/search/issues'
KINDS = ('pr', 'issue')
PER_PAGE = 100

_warned_no_token = False


def _github_headers() -> Dict[str, str]:
    global _warned_no_token
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    token = getattr(settings, 'GITHUB_TOKEN', '') or ''
    if token:
        headers['Authorization'] = f'Bearer {token}'
    elif not _warned_no_token:
        logger.warning('GITHUB_TOKEN is not set; GitHub search is limited to 10 requests a minute.')
        _warned_no_token = True
    return headers


def build_search_query(hashtag: str, kind: str, since_date: str) -> str:
    qualifier = 'is:pr' if kind == 'pr' else 'is:issue'
    return f'"#{hashtag.lstrip("#")}" in:body,title {qualifier} created:>={since_date}'


def search_github(hashtag: str, kind: str, since_date: str) -> List[Dict[str, Any]]:
    data = http_get(
        GITHUB_SEARCH_URL,
        f'GitHub {kind} search',
        params={'q': build_search_query(hashtag, kind, since_date), 'per_page': PER_PAGE,
                'sort': 'created', 'order': 'desc'},
        headers=_github_headers(),
    )
    return data.get('items') or []


def repo_from_item(item: Dict[str, Any]) -> str:
    """'owner/name' from repository_url (https://api.github.com/repos/owner/name)."""
    url = item.get('repository_url') or ''
    marker = '/repos/'
    return url.split(marker, 1)[1] if marker in url else ''


def harvest_github(ctx: HarvestContext, quests: List[Quest]) -> None:
    event = ctx.event
    ctx.platform(PLATFORM)
    since = event.start_time.strftime('%Y-%m-%d')

    wanted_kinds = set()
    for quest in quests:
        kinds = (quest.validation_rules or {}).get('kinds') or list(KINDS)
        wanted_kinds.update(k for k in kinds if k in KINDS)

    results: Dict[str, List[Dict[str, Any]]] = {}
    for kind in sorted(wanted_kinds):
        try:
            results[kind] = search_github(event.hashtag, kind, since)
        except HarvestError as exc:
            # 403/429 when rate limited: count it and carry on with whatever else we have.
            ctx.error(PLATFORM, str(exc))
            results[kind] = []

    for quest in quests:
        rules = quest.validation_rules or {}
        kinds = [k for k in (rules.get('kinds') or list(KINDS)) if k in KINDS]
        allowed = {o.lower() for o in (rules.get('allowed_owners') or []) if o}
        for kind in kinds:
            for item in results.get(kind, []):
                text = f"{item.get('title') or ''}\n{item.get('body') or ''}"
                if not hashtag_matches(text, event.hashtag):
                    continue
                created_at = parse_timestamp(item.get('created_at'))
                if not counts_for_quest(event, quest, created_at):
                    continue
                repo = repo_from_item(item)
                if allowed and repo.split('/', 1)[0].lower() not in allowed:
                    continue
                upsert_submission(
                    ctx,
                    platform=PLATFORM,
                    quest=quest,
                    external_id=f"{item.get('id')}/q{quest.id}",
                    external_url=item.get('html_url', ''),
                    author_username=(item.get('user') or {}).get('login', ''),
                    contributed_at=created_at,
                    element_count=1,
                    diff_payload={
                        'kind': kind,
                        'repo': repo,
                        'number': item.get('number'),
                        'title': item.get('title', ''),
                        'state': item.get('state', ''),
                    },
                )
