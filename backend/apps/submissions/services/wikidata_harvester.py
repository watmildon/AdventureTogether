"""
Wikidata harvesters.

- `wikidata_entry` quests: any Wikidata edit whose edit summary carries the event hashtag.
  Candidate items come from a hashtag search plus the recent contributions of team members who
  shared a Wikimedia username (edit summaries are not in the search index, so the search alone
  rarely finds hashtagged edits). One submission per matching revision.
- `wikidata_statement` quests: edits to one named item (validation_rules.qid) whose summary
  carries the hashtag and mentions one of the configured properties.
"""

import re
from datetime import datetime
from typing import Any, Dict, List

from django.conf import settings

from apps.quests.models import Quest
from apps.teams.models import TeamMembership
from .harvest_common import (
    HarvestContext,
    HarvestError,
    counts_for_quest,
    http_get,
    parse_timestamp,
    quest_window_start,
    to_utc_iso,
    upsert_submission,
)
from .tag_matcher import hashtag_matches

PLATFORM = 'wikidata'
SEARCH_LIMIT = 50
ENTRY_REVISION_LIMIT = 20
STATEMENT_REVISION_LIMIT = 100
CONTRIBS_LIMIT = 500


def parse_wikidata_search_response(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Search hits as candidate items: {external_id (pageid), platform, external_url, title, snippet}."""
    results = []
    for item in (data.get('query') or {}).get('search') or []:
        title = item.get('title', '')
        results.append({
            'external_id': str(item.get('pageid')),
            'platform': PLATFORM,
            'external_url': f'https://www.wikidata.org/wiki/{title}',
            'title': title,
            'snippet': item.get('snippet', ''),
        })
    return results


def search_wikidata_items(hashtag: str) -> List[Dict[str, Any]]:
    data = http_get(settings.WIKIDATA_API, 'Wikidata search', params={
        'action': 'query',
        'list': 'search',
        'srsearch': f"#{hashtag.lstrip('#')}",
        'srnamespace': '0',
        'srlimit': str(SEARCH_LIMIT),
        'format': 'json',
    })
    return parse_wikidata_search_response(data)


def fetch_item_revisions(title: str, start: datetime, end: datetime, limit: int) -> List[Dict[str, Any]]:
    """Revisions of one page made between start and end, newest first."""
    data = http_get(settings.WIKIDATA_API, 'Wikidata revisions', params={
        'action': 'query',
        'titles': title,
        'prop': 'revisions',
        'rvprop': 'ids|user|timestamp|comment',
        'rvlimit': str(limit),
        'rvstart': to_utc_iso(end),   # rvdir=older: start at the newer bound
        'rvend': to_utc_iso(start),
        'format': 'json',
    })
    revisions = []
    for page in ((data.get('query') or {}).get('pages') or {}).values():
        for rev in page.get('revisions') or []:
            revisions.append({**rev, 'title': page.get('title', title)})
    return revisions


def fetch_user_contributions(usernames: List[str], start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Edits by the given accounts between start and end (up to 50 accounts per call)."""
    contributions = []
    for i in range(0, len(usernames), 50):
        data = http_get(settings.WIKIDATA_API, 'Wikidata contributions', params={
            'action': 'query',
            'list': 'usercontribs',
            'ucuser': '|'.join(usernames[i:i + 50]),
            'ucprop': 'ids|title|timestamp|comment',
            'uclimit': str(CONTRIBS_LIMIT),
            'ucstart': to_utc_iso(end),
            'ucend': to_utc_iso(start),
            'format': 'json',
        })
        contributions.extend((data.get('query') or {}).get('usercontribs') or [])
    return contributions


def _member_wikimedia_usernames(ctx: HarvestContext) -> List[str]:
    names = (
        TeamMembership.objects.filter(team__event=ctx.event)
        .exclude(wikimedia_username='')
        .values_list('wikimedia_username', flat=True)
    )
    return sorted({n.strip() for n in names if n and n.strip()})


def _diff_url(revid: Any) -> str:
    return f'https://www.wikidata.org/w/index.php?diff={revid}'


def harvest_wikidata_entries(ctx: HarvestContext, quests: List[Quest]) -> None:
    event = ctx.event
    ctx.platform(PLATFORM)
    revisions: Dict[str, Dict[str, Any]] = {}

    try:
        candidates = search_wikidata_items(event.hashtag)
    except HarvestError as exc:
        ctx.error(PLATFORM, str(exc))
        candidates = []
    for candidate in candidates:
        try:
            revs = fetch_item_revisions(candidate['title'], event.start_time, event.end_time,
                                        ENTRY_REVISION_LIMIT)
        except HarvestError as exc:
            ctx.error(PLATFORM, f"{candidate['title']}: {exc}")
            continue
        for rev in revs:
            revisions.setdefault(str(rev.get('revid')), rev)

    usernames = _member_wikimedia_usernames(ctx)
    if usernames:
        try:
            for rev in fetch_user_contributions(usernames, event.start_time, event.end_time):
                revisions.setdefault(str(rev.get('revid')), rev)
        except HarvestError as exc:
            ctx.error(PLATFORM, str(exc))

    ordered_quests = sorted(quests, key=lambda q: q.id)
    for revid, rev in revisions.items():
        comment = rev.get('comment', '')
        if not hashtag_matches(comment, event.hashtag):
            continue
        edited_at = parse_timestamp(rev.get('timestamp'))
        quest = next((q for q in ordered_quests if counts_for_quest(event, q, edited_at)), None)
        if quest is None:
            continue
        upsert_submission(
            ctx,
            platform=PLATFORM,
            quest=quest,
            external_id=revid,
            external_url=_diff_url(revid),
            author_username=rev.get('user', ''),
            contributed_at=edited_at,
            element_count=1,
            diff_payload={'entity_id': rev.get('title', ''), 'revid': revid, 'comment': comment},
        )


def properties_mentioned(comment: str, properties: List[str]) -> List[str]:
    """
    Which of the configured property ids appear as whole tokens in an edit summary
    (auto-summaries contain e.g. `[[Property:P84]]`; P8 does not match P84).
    """
    found = []
    for prop in properties or []:
        pid = str(prop).strip().upper()
        if pid and re.search(r'(?<![A-Za-z0-9])' + re.escape(pid) + r'(?!\d)', comment or ''):
            found.append(pid)
    return found


def harvest_wikidata_statements(ctx: HarvestContext, quests: List[Quest]) -> None:
    event = ctx.event
    ctx.platform(PLATFORM)
    for quest in quests:
        rules = quest.validation_rules or {}
        qid = str(rules.get('qid') or '').strip()
        if not qid:
            ctx.warnings.append(f'wikidata_statement quest {quest.id} has no qid; skipped')
            continue
        properties = rules.get('properties') or []
        try:
            revs = fetch_item_revisions(qid, quest_window_start(event, quest), event.end_time,
                                        STATEMENT_REVISION_LIMIT)
        except HarvestError as exc:
            ctx.error(PLATFORM, f'{qid}: {exc}')
            continue

        for rev in revs:
            comment = rev.get('comment', '')
            if not hashtag_matches(comment, event.hashtag):
                continue
            touched = properties_mentioned(comment, properties)
            if properties and not touched:
                continue
            edited_at = parse_timestamp(rev.get('timestamp'))
            if not counts_for_quest(event, quest, edited_at):
                continue
            revid = str(rev.get('revid'))
            upsert_submission(
                ctx,
                platform=PLATFORM,
                quest=quest,
                external_id=f'{revid}/q{quest.id}',
                external_url=_diff_url(revid),
                author_username=rev.get('user', ''),
                contributed_at=edited_at,
                element_count=1,
                diff_payload={'qid': qid, 'revid': revid, 'properties_touched': touched,
                              'comment': comment},
            )
