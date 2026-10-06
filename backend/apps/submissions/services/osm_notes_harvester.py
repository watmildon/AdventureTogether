"""
OpenStreetMap Notes harvester (`osm_notes` quests).

Fetches notes in the event perimeter's bounding box from the public OSM Notes API and credits
notes that were closed during the event window with the hashtag in one of their comments.
"""

from typing import Any, Dict, List, Optional

from django.conf import settings

from apps.quests.models import Quest
from .harvest_common import (
    HarvestContext,
    HarvestError,
    counts_for_quest,
    http_get,
    parse_timestamp,
    point_in_quest_area,
    upsert_submission,
)
from .tag_matcher import hashtag_matches

PLATFORM = 'osm_notes'
NOTES_LIMIT = 100


def fetch_notes(bbox) -> List[Dict[str, Any]]:
    """Notes (open and closed) in a (min_lon, min_lat, max_lon, max_lat) box, newest first."""
    min_lon, min_lat, max_lon, max_lat = bbox
    base = settings.OSM_API_BASE.rstrip('/')
    data = http_get(
        f'{base}/notes.json',
        'OSM notes',
        params={
            'bbox': f'{min_lon:.6f},{min_lat:.6f},{max_lon:.6f},{max_lat:.6f}',
            'closed': -1,
            'limit': NOTES_LIMIT,
        },
    )
    return data.get('features') or []


def qualifying_note(feature: Dict[str, Any], hashtag: str) -> Optional[Dict[str, Any]]:
    """
    Returns {id, lat, lon, closed_at, author, comments, status} when the note is closed and some
    comment carries the hashtag, else None. The author is whoever closed the note, falling back
    to the user of the hashtag comment.
    """
    props = feature.get('properties') or {}
    if props.get('status') != 'closed':
        return None
    comments = props.get('comments') or []
    tagged = [c for c in comments if hashtag_matches(c.get('text', ''), hashtag)]
    if not tagged:
        return None

    closer = next((c for c in reversed(comments) if c.get('action') == 'closed'), None)
    author = (closer or {}).get('user') or next((c.get('user') for c in tagged if c.get('user')), '')
    closed_at = parse_timestamp(props.get('closed_at') or props.get('date_closed')
                                or (closer or {}).get('date'))
    coords = (feature.get('geometry') or {}).get('coordinates') or [None, None]
    return {
        'id': props.get('id'),
        'lon': coords[0],
        'lat': coords[1],
        'closed_at': closed_at,
        'author': author,
        'status': props.get('status'),
        'comments': [
            {k: c.get(k) for k in ('date', 'user', 'action', 'text')} for c in comments
        ],
    }


def harvest_osm_notes(ctx: HarvestContext, quests: List[Quest]) -> None:
    event = ctx.event
    ctx.platform(PLATFORM)
    try:
        features = fetch_notes(event.bounding_polygon.extent)
    except HarvestError as exc:
        ctx.error(PLATFORM, str(exc))
        return

    for feature in features:
        note = qualifying_note(feature, event.hashtag)
        if not note or note['id'] is None or note['lat'] is None:
            continue
        for quest in quests:
            if not counts_for_quest(event, quest, note['closed_at']):
                continue
            if not point_in_quest_area(event, quest, note['lat'], note['lon']):
                continue
            upsert_submission(
                ctx,
                platform=PLATFORM,
                quest=quest,
                external_id=f"{note['id']}/q{quest.id}",
                external_url=f"https://www.openstreetmap.org/note/{note['id']}",
                author_username=note['author'],
                contributed_at=note['closed_at'],
                element_count=1,
                diff_payload={'status': note['status'], 'comments': note['comments']},
            )
