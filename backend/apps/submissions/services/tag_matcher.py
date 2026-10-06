"""
Hashtag matching and contributor-to-team attribution shared by the harvesters.
"""

import re
from typing import Any, Mapping, Optional, Union

from apps.events.models import Event
from apps.teams.models import Team, TeamMembership

# Which TeamMembership username field identifies a contributor on each platform.
PLATFORM_USERNAME_FIELDS = {
    'osm': 'osm_username',
    'osm_notes': 'osm_username',
    'ohm': 'osm_username',
    'commons': 'wikimedia_username',
    'wikidata': 'wikimedia_username',
    'github': 'github_username',
    # MapRoulette users sign in with OpenStreetMap, so their OSM name is what we learn.
    'maproulette': 'osm_username',
}

# Platforms without a username field on TeamMembership, where the contributor picks a free-form
# name (a Mangrove review's nickname). Members are told to use their display name there, so it
# is tried first.
DISPLAY_NAME_FIRST_PLATFORMS = {'mangrove'}


def _normalize_hashtag(hashtag: str) -> str:
    return (hashtag or '').strip().lstrip('#').lower()


def _text_has_hashtag(text: str, tag: str) -> bool:
    """`#tag` as a whole token, case-insensitive: '#FOSS4GNA2026' does not match '#FOSS4GNA2026hunt'."""
    if not text or not tag:
        return False
    pattern = r'(?<![\w#])#' + re.escape(tag) + r'(?!\w)'
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def hashtag_matches(text_or_tags: Union[str, Mapping[str, Any], None], hashtag: str) -> bool:
    """
    Whether a contribution carries the event hashtag.

    - A string (edit summary, note comment, PR body) matches when it contains `#tag` as a token.
    - A mapping of OSM changeset tags matches when the `hashtags` tag (semicolon-separated, as
      written by iD, StreetComplete and others; the leading `#` is optional there) lists the tag,
      or when the `comment` tag contains `#tag`.
    """
    tag = _normalize_hashtag(hashtag)
    if not tag or not text_or_tags:
        return False

    if isinstance(text_or_tags, Mapping):
        listed = str(text_or_tags.get('hashtags', '') or '')
        for entry in listed.split(';'):
            if entry.strip().lstrip('#').lower() == tag:
                return True
        return _text_has_hashtag(str(text_or_tags.get('comment', '') or ''), tag)

    return _text_has_hashtag(str(text_or_tags), tag)


def match_author_to_team(event: Event, author_username: str, platform: Optional[str] = None) -> Optional[Team]:
    """
    Finds the team in this event that the contributor belongs to.

    The platform-specific username a member shared when joining (osm_username for OSM, OSM Notes
    and OpenHistoricalMap; wikimedia_username for Commons and Wikidata; github_username for
    GitHub; osm_username also for MapRoulette) is checked first, then the member's
    user_identifier and display_name. For Mangrove, where the author is a free-form review
    nickname, display_name is checked first and then user_identifier. All comparisons are
    case-insensitive.
    """
    if not author_username:
        return None

    memberships = TeamMembership.objects.filter(team__event=event).select_related('team')

    candidates = []
    username_field = PLATFORM_USERNAME_FIELDS.get(platform or '')
    if username_field:
        candidates.append({f'{username_field}__iexact': author_username})
    if platform in DISPLAY_NAME_FIRST_PLATFORMS:
        candidates.append({'display_name__iexact': author_username})
        candidates.append({'user_identifier__iexact': author_username})
    else:
        candidates.append({'user_identifier__iexact': author_username})
        candidates.append({'display_name__iexact': author_username})

    for lookup in candidates:
        membership = memberships.filter(**lookup).order_by('joined_at', 'id').first()
        if membership:
            return membership.team
    return None
