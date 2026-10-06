"""
Mangrove Reviews harvester (`mangrove_review` quests).

Mangrove (https://mangrove.reviews) is an open dataset of reviews signed with the reviewer's
own key pair; no account is needed. `GET {MANGROVE_API}/geo` returns the place reviews whose
subject (a `geo:` URI) lies in a bounding box. A review counts when its place is inside the
quest's area, it was written during the window, and (by default) its opinion carries the event
hashtag. The reviewer is identified only by the nickname they chose, so participants are asked
to use their display name there.
"""

import base64
import hashlib
import json
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, unquote

from django.conf import settings

from apps.quests.models import Quest
from .harvest_common import (
    HarvestContext,
    HarvestError,
    counts_for_quest,
    http_get,
    point_in_quest_area,
    quest_bbox,
    union_bbox,
    upsert_submission,
)
from .tag_matcher import hashtag_matches

PLATFORM = 'mangrove'
MANGROVE_HTTP_TIMEOUT = 30
REVIEW_URL = 'https://mangrove.reviews/list?signature={signature}'
# Submission.external_id is a 255-character field and carries a "/q{quest id}" suffix.
EXTERNAL_ID_MAX = 255


def fetch_geo_reviews(bbox) -> List[Dict[str, Any]]:
    """Place reviews whose subject lies in a (min_lon, min_lat, max_lon, max_lat) box."""
    min_lon, min_lat, max_lon, max_lat = bbox
    base = settings.MANGROVE_API.rstrip('/')
    data = http_get(
        f'{base}/geo',
        'Mangrove reviews',
        params={'xmin': f'{min_lon:.6f}', 'ymin': f'{min_lat:.6f}',
                'xmax': f'{max_lon:.6f}', 'ymax': f'{max_lat:.6f}'},
        timeout=MANGROVE_HTTP_TIMEOUT,
    )
    return data.get('reviews') or []


def decode_jwt_payload(token: Any) -> Dict[str, Any]:
    """
    The claims of a review's JWT (its middle, base64url-encoded segment). The signature is not
    checked: we only read what the reviewer published. Returns {} when it cannot be decoded.
    """
    parts = token.split('.') if isinstance(token, str) else []
    if len(parts) != 3:
        return {}
    segment = parts[1] + '=' * (-len(parts[1]) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(segment.encode('ascii')))
    except (ValueError, UnicodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def review_payload(review: Dict[str, Any]) -> Dict[str, Any]:
    payload = review.get('payload')
    if isinstance(payload, dict) and payload:
        return payload
    return decode_jwt_payload(review.get('jwt'))


def subject_coordinates(sub: Any, review: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """
    (lat, lon) of a place review: from its `geo:lat,lon?q=...&u=...` subject, falling back to
    the `geo.coordinates` the API adds. (None, None) for non-place subjects.
    """
    if isinstance(sub, str) and sub.startswith('geo:'):
        coords = sub[4:].split('?', 1)[0].split(';', 1)[0].split(',')
        try:
            return float(coords[0]), float(coords[1])
        except (IndexError, ValueError):
            pass
    coords = ((review.get('geo') or {}).get('coordinates')) or {}
    try:
        return float(coords['lat']), float(coords['lon'])
    except (KeyError, TypeError, ValueError):
        return None, None


def place_name(sub: Any) -> str:
    """The `q=` place name in a geo URI subject ('' when absent)."""
    if not isinstance(sub, str) or '?' not in sub:
        return ''
    for part in sub.split('?', 1)[1].split('&'):
        if part.startswith('q='):
            return unquote(part[2:])
    return ''


def review_author(metadata: Dict[str, Any], kid: Any) -> str:
    """The reviewer's nickname, or "anonymous key <12 hex>" derived from their public key."""
    nickname = str(metadata.get('nickname') or '').strip()
    if nickname:
        return nickname
    digest = hashlib.sha256(str(kid or '').encode('utf-8')).hexdigest()[:12]
    return f'anonymous key {digest}'


def review_external_id(signature: str, quest_id: int) -> str:
    """`{signature}/q{quest}`; a signature too long for the column is replaced by its sha256."""
    suffix = f'/q{quest_id}'
    if len(signature) + len(suffix) > EXTERNAL_ID_MAX:
        signature = 'sha256:' + hashlib.sha256(signature.encode('utf-8')).hexdigest()
    return f'{signature}{suffix}'


def _timestamp(iat: Any) -> Optional[datetime]:
    """A review's `iat` (unix seconds) as an aware UTC datetime."""
    try:
        return datetime.fromtimestamp(int(iat), tz=dt_timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def parse_review(review: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The fields the quests need from one /geo item, or None when it is not a usable place review."""
    signature = str(review.get('signature') or '')
    payload = review_payload(review)
    if not signature or not payload:
        return None
    sub = payload.get('sub')
    lat, lon = subject_coordinates(sub, review)
    if lat is None:
        return None
    metadata = payload.get('metadata') if isinstance(payload.get('metadata'), dict) else {}
    try:
        rating = int(payload['rating']) if payload.get('rating') is not None else None
    except (TypeError, ValueError):
        rating = None
    return {
        'signature': signature,
        'sub': sub,
        'place': place_name(sub),
        'lat': lat,
        'lon': lon,
        'rating': rating,
        'opinion': str(payload.get('opinion') or ''),
        'created_at': _timestamp(payload.get('iat')),
        'author': review_author(metadata, review.get('kid')),
        'nickname': str(metadata.get('nickname') or ''),
        'osm_id': metadata.get('osm_id') or '',
        'client_id': metadata.get('client_id') or '',
    }


def _int_rule(rules: Dict[str, Any], key: str, default: Optional[int]) -> Optional[int]:
    value = rules.get(key, default)
    if value in (None, ''):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def review_counts(event, quest: Quest, review: Dict[str, Any]) -> bool:
    """Whether a parsed review satisfies the quest's rules, window and area."""
    rules = quest.validation_rules or {}
    if not counts_for_quest(event, quest, review['created_at']):
        return False
    if not point_in_quest_area(event, quest, review['lat'], review['lon']):
        return False
    if rules.get('require_hashtag', True) is not False and not hashtag_matches(review['opinion'], event.hashtag):
        return False
    if len(review['opinion'].strip()) < (_int_rule(rules, 'min_opinion_chars', 0) or 0):
        return False
    min_rating = _int_rule(rules, 'min_rating', None)
    if min_rating is not None and (review['rating'] is None or review['rating'] < min_rating):
        return False
    return True


def harvest_mangrove(ctx: HarvestContext, quests: List[Quest]) -> None:
    event = ctx.event
    ctx.platform(PLATFORM)
    # One request covers every quest: the union of their areas' boxes.
    bbox = union_bbox(quest_bbox(event, quest) for quest in quests)
    if bbox is None:
        return
    try:
        items = fetch_geo_reviews(bbox)
    except HarvestError as exc:
        ctx.error(PLATFORM, str(exc))
        return

    for item in items:
        review = parse_review(item) if isinstance(item, dict) else None
        if review is None:
            continue
        for quest in quests:
            if not review_counts(event, quest, review):
                continue
            upsert_submission(
                ctx,
                platform=PLATFORM,
                quest=quest,
                external_id=review_external_id(review['signature'], quest.id),
                external_url=REVIEW_URL.format(signature=quote(review['signature'], safe='')),
                author_username=review['author'],
                contributed_at=review['created_at'],
                element_count=1,
                diff_payload={
                    'sub': review['sub'],
                    'place': review['place'],
                    'rating': review['rating'],
                    'opinion': review['opinion'],
                    # Value scoring's "description" source reads `text`.
                    'text': review['opinion'],
                    'nickname': review['nickname'],
                    'osm_id': review['osm_id'],
                    'client_id': review['client_id'],
                    'lat': review['lat'],
                    'lon': review['lon'],
                },
            )
