"""
Wikidata harvesters.

Wikidata's own UI (and tools such as WikiShootMe) write automatic edit summaries, so the event
hashtag is not required by default: `validation_rules.require_hashtag` is false unless a quest
sets it, and edits are then found and credited through the `wikimedia_username` members shared.

- `wikidata_entry` quests: any Wikidata edit by a member during the event. Candidates are the
  members' contributions; with require_hashtag a hashtag search of items is added (edit summaries
  are not in the search index, so the search alone rarely finds hashtagged edits) and the
  summary must carry the hashtag. One submission per matching revision.
- `wikidata_statement` quests: edits to one named item (validation_rules.qid) that mention one of
  the configured properties, by a member (or, with require_hashtag, by anyone whose summary
  carries the hashtag).
- `wikidata_area` quests: statements added to items whose coordinates (P625) are inside the quest
  area, found in members' contributions; one submission per (item, quest). Usually P18 (image),
  added with WikiShootMe.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings

from apps.quests.models import Quest
from apps.teams.models import TeamMembership
from .harvest_common import (
    HarvestContext,
    HarvestError,
    counts_for_quest,
    http_get,
    parse_timestamp,
    point_in_quest_area,
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
# wikidata_area: usercontribs pages of 100 per member, at most AREA_CONTRIBS_MAX_PAGES of them,
# and entity lookups of at most 50 ids (the wbgetentities limit for normal accounts).
AREA_CONTRIBS_LIMIT = 100
AREA_CONTRIBS_MAX_PAGES = 5
ENTITY_BATCH = 50
DEFAULT_AREA_PROPERTIES = ['P18']
# Automatic summaries of edits that add or change a statement: the Wikidata UI and the Commons
# app write wbsetclaim-create (new statement) and wbsetclaim-update (changed value); WikiShootMe
# and other API tools write wbcreateclaim-create. Removals, qualifier/reference edits and
# whole-entity edits (wbeditentity-*) do not count.
CLAIM_SUMMARY_PREFIXES = ('/* wbsetclaim-create', '/* wbcreateclaim-create', '/* wbsetclaim-update')


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


def _norm_username(name: Any) -> str:
    """MediaWiki treats `_` and space alike and capitalises the first letter; compare loosely."""
    return str(name or '').replace('_', ' ').strip().lower()


def requires_hashtag(quest: Quest) -> bool:
    """Wikidata quests only require the hashtag when validation_rules.require_hashtag is true."""
    return (quest.validation_rules or {}).get('require_hashtag', False) is True


def harvest_wikidata_entries(ctx: HarvestContext, quests: List[Quest]) -> None:
    event = ctx.event
    ctx.platform(PLATFORM)
    revisions: Dict[str, Dict[str, Any]] = {}

    # The hashtag search only helps quests that require the hashtag; members' contributions
    # are read either way.
    candidates = []
    if any(requires_hashtag(q) for q in quests):
        try:
            candidates = search_wikidata_items(event.hashtag)
        except HarvestError as exc:
            ctx.error(PLATFORM, str(exc))
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
    members = {_norm_username(name) for name in usernames}

    ordered_quests = sorted(quests, key=lambda q: q.id)
    for revid, rev in revisions.items():
        comment = rev.get('comment', '')
        # A revision counts for a quest that requires the hashtag only when its summary has it,
        # and for any other quest when it has it or was made by a member.
        has_hashtag = hashtag_matches(comment, event.hashtag)
        by_member = _norm_username(rev.get('user')) in members
        edited_at = parse_timestamp(rev.get('timestamp'))
        quest = next((q for q in ordered_quests
                      if (has_hashtag or (by_member and not requires_hashtag(q)))
                      and counts_for_quest(event, q, edited_at)),
                     None)
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
    members = {_norm_username(name) for name in _member_wikimedia_usernames(ctx)}
    for quest in quests:
        rules = quest.validation_rules or {}
        qid = str(rules.get('qid') or '').strip()
        if not qid:
            ctx.warnings.append(f'wikidata_statement quest {quest.id} has no qid; skipped')
            continue
        properties = rules.get('properties') or []
        hashtag_required = requires_hashtag(quest)
        if not hashtag_required and not members:
            continue  # nobody could be credited, so do not read the item's history
        try:
            revs = fetch_item_revisions(qid, quest_window_start(event, quest), event.end_time,
                                        STATEMENT_REVISION_LIMIT)
        except HarvestError as exc:
            ctx.error(PLATFORM, f'{qid}: {exc}')
            continue

        for rev in revs:
            comment = rev.get('comment', '')
            if hashtag_required:
                if not hashtag_matches(comment, event.hashtag):
                    continue
            elif _norm_username(rev.get('user')) not in members:
                # Without the hashtag only members' edits are credited (by wikimedia_username).
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


# --- wikidata_area -------------------------------------------------------------------------

def area_properties(quest: Quest) -> List[str]:
    """The quest's property ids (validation_rules.properties, P18 by default); invalid ids dropped."""
    raw = (quest.validation_rules or {}).get('properties')
    items = raw if isinstance(raw, (list, tuple)) else str(raw or '').replace(',', ' ').split()
    props = []
    for item in items:
        pid = str(item).strip().upper()
        if re.fullmatch(r'P\d+', pid) and pid not in props:
            props.append(pid)
    return props or list(DEFAULT_AREA_PROPERTIES)


def is_claim_summary(comment: str) -> bool:
    """Whether an automatic summary is a statement creation or value update (CLAIM_SUMMARY_PREFIXES)."""
    return (comment or '').startswith(CLAIM_SUMMARY_PREFIXES)


def fetch_member_contributions(ctx: HarvestContext, username: str, start: datetime,
                               end: datetime) -> List[Dict[str, Any]]:
    """
    One member's item edits between start and end, newest first: pages of AREA_CONTRIBS_LIMIT,
    following `uccontinue` for at most AREA_CONTRIBS_MAX_PAGES pages (a warning is recorded when
    the cap cuts the listing short).
    """
    contributions: List[Dict[str, Any]] = []
    cont: Dict[str, str] = {}
    for _page in range(AREA_CONTRIBS_MAX_PAGES):
        data = http_get(settings.WIKIDATA_API, 'Wikidata contributions', params={
            'action': 'query',
            'list': 'usercontribs',
            'ucuser': username,
            'ucnamespace': '0',
            'ucprop': 'ids|title|timestamp|comment',
            'uclimit': str(AREA_CONTRIBS_LIMIT),
            'ucstart': to_utc_iso(end),   # ucdir=older: start at the newer bound
            'ucend': to_utc_iso(start),
            'format': 'json',
            **cont,
        })
        contributions.extend((data.get('query') or {}).get('usercontribs') or [])
        uccontinue = (data.get('continue') or {}).get('uccontinue')
        if not uccontinue:
            return contributions
        cont = {'uccontinue': uccontinue, 'continue': (data.get('continue') or {}).get('continue', '-||')}
    ctx.warnings.append(f'Wikidata contributions of {username} stopped at {AREA_CONTRIBS_MAX_PAGES} pages')
    return contributions


def _first_coordinate(claims: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """(lat, lon) of the item's P625 statement: a preferred one first, deprecated ones never."""
    statements = [c for c in claims.get('P625') or [] if c.get('rank') != 'deprecated']
    statements.sort(key=lambda c: c.get('rank') != 'preferred')
    for claim in statements:
        value = ((claim.get('mainsnak') or {}).get('datavalue') or {}).get('value') or {}
        try:
            return float(value['latitude']), float(value['longitude'])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def resolve_item_coordinates(ctx: HarvestContext, qids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    {qid: {'coords': (lat, lon) or None, 'label': English label or ''}} for the given items, from
    `wbgetentities` in batches of ENTITY_BATCH (each request counted in `entity_lookups`).
    Results, including items without coordinates, are cached for the run; a failed batch is
    counted as an error and its items are left out.
    """
    missing = [q for q in dict.fromkeys(qids) if ('wikidata-entity', q) not in ctx.cache]
    for i in range(0, len(missing), ENTITY_BATCH):
        batch = missing[i:i + ENTITY_BATCH]
        ctx.platform(PLATFORM)['entity_lookups'] += 1
        try:
            data = http_get(settings.WIKIDATA_API, 'Wikidata entities', params={
                'action': 'wbgetentities',
                'ids': '|'.join(batch),
                # Labels come with the same request, so they are cheap to include.
                'props': 'claims|labels',
                'languages': 'en',
                'format': 'json',
            })
        except HarvestError as exc:
            ctx.error(PLATFORM, str(exc))
            continue
        entities = data.get('entities') or {}
        for qid in batch:
            entity = entities.get(qid) or {}
            label = ((entity.get('labels') or {}).get('en') or {}).get('value', '')
            ctx.cache[('wikidata-entity', qid)] = {
                'coords': _first_coordinate(entity.get('claims') or {}),
                'label': label,
            }
    return {q: ctx.cache[('wikidata-entity', q)] for q in qids if ('wikidata-entity', q) in ctx.cache}


def harvest_wikidata_area(ctx: HarvestContext, quests: List[Quest]) -> None:
    """
    Credits statements (P18 by default) that members added to items located in the quest area.

    Members' item edits in the window are read with `list=usercontribs` (one listing per member
    who shared a `wikimedia_username`). An edit counts for a quest when its automatic summary is a
    statement creation or update (CLAIM_SUMMARY_PREFIXES) that mentions one of the quest's
    properties, it falls in the quest window (and carries the hashtag when require_hashtag is
    true), and the item's P625 coordinates are inside the quest area. Each (item, quest) pair is
    one submission, credited to the member with the earliest qualifying edit.
    """
    event = ctx.event
    # wbgetentities requests, so hosts can see the load on Wikidata.
    ctx.platform(PLATFORM).setdefault('entity_lookups', 0)
    usernames = _member_wikimedia_usernames(ctx)
    if not usernames:
        ctx.warnings.append('No member has shared a Wikimedia username; skipped wikidata_area quests')
        return

    start = min(quest_window_start(event, quest) for quest in quests)
    all_properties = {pid for quest in quests for pid in area_properties(quest)}
    candidates = []  # (member, revision) pairs that may count for some quest
    for username in usernames:
        try:
            contributions = fetch_member_contributions(ctx, username, start, event.end_time)
        except HarvestError as exc:
            ctx.error(PLATFORM, f'{username}: {exc}')
            continue
        for rev in contributions:
            comment = rev.get('comment', '')
            if not re.fullmatch(r'Q\d+', str(rev.get('title', ''))):
                continue
            if is_claim_summary(comment) and properties_mentioned(comment, sorted(all_properties)):
                candidates.append((username, rev))
    if not candidates:
        return

    entities = resolve_item_coordinates(ctx, [rev['title'] for _user, rev in candidates])

    for quest in quests:
        properties = area_properties(quest)
        hashtag_required = requires_hashtag(quest)
        # Earliest qualifying edit per item: (member, revision, contributed_at, properties touched)
        best: Dict[str, tuple] = {}
        for username, rev in candidates:
            comment = rev.get('comment', '')
            touched = properties_mentioned(comment, properties)
            if not touched:
                continue
            if hashtag_required and not hashtag_matches(comment, event.hashtag):
                continue
            edited_at = parse_timestamp(rev.get('timestamp'))
            if not counts_for_quest(event, quest, edited_at):
                continue
            qid = rev['title']
            coords = (entities.get(qid) or {}).get('coords')
            if coords is None or not point_in_quest_area(event, quest, coords[0], coords[1]):
                continue
            if qid not in best or edited_at < best[qid][2]:
                best[qid] = (username, rev, edited_at, touched)

        for qid, (username, rev, edited_at, touched) in best.items():
            lat, lon = entities[qid]['coords']
            payload = {
                'qid': qid,
                'properties_touched': touched,
                'revid': str(rev.get('revid')),
                'comment': rev.get('comment', ''),
                'lat': lat,
                'lon': lon,
            }
            if entities[qid].get('label'):
                payload['label'] = entities[qid]['label']
            upsert_submission(
                ctx,
                platform=PLATFORM,
                quest=quest,
                external_id=f'{qid}/q{quest.id}',
                external_url=f'https://www.wikidata.org/wiki/{qid}',
                author_username=username,
                contributed_at=edited_at,
                element_count=1,
                diff_payload=payload,
            )
