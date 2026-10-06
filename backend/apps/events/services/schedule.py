"""
Conference schedule import (pretalx / frab JSON export).

Hosts can point an event at a schedule export so quests can be linked to the sessions that
inspired them. The export is parsed into a flat list of sessions whose shape matches
Quest.inspired_by, so a client can copy a session straight into a quest.
"""

import hashlib
from typing import Any, Dict, List

import requests
from django.conf import settings
from django.core.cache import cache

# Schedules change rarely during a conference; 10 minutes keeps the picker responsive
# without hammering the schedule host.
SCHEDULE_CACHE_SECONDS = 10 * 60
SCHEDULE_FETCH_TIMEOUT_SECONDS = 15


class ScheduleFetchError(Exception):
    """Raised when a schedule export cannot be downloaded or parsed."""


def _cache_key(url: str) -> str:
    # Hash the URL so arbitrary characters and lengths are safe for any cache backend.
    return 'event-schedule:' + hashlib.sha256(url.encode('utf-8')).hexdigest()


def _speaker_names(persons) -> List[str]:
    names = []
    for person in persons or []:
        if isinstance(person, dict):
            name = person.get('public_name') or person.get('name')
            if name:
                names.append(name)
    return names


def _session_from_talk(talk: Dict[str, Any], room_name: str) -> Dict[str, Any]:
    """Maps one frab talk object onto the Quest.inspired_by shape (plus `type`)."""
    return {
        'code': talk.get('code') or str(talk.get('guid') or talk.get('id') or ''),
        'title': talk.get('title', ''),
        'speakers': _speaker_names(talk.get('persons')),
        'start': talk.get('date'),
        'room': talk.get('room') or room_name,
        'track': talk.get('track'),
        'url': talk.get('url'),
        'type': talk.get('type'),
    }


def parse_frab_schedule(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Flattens a frab-format schedule (schedule.conference.days[].rooms{room: [talk]}) into
    a list of {code, title, speakers, start, room, track, url, type} dicts sorted by start.
    `start` is the talk's full ISO 8601 `date` field, not the bare "HH:MM" `start`.
    Raises ScheduleFetchError if the document does not have the expected structure.
    """
    try:
        days = data['schedule']['conference']['days']
    except (KeyError, TypeError) as exc:
        raise ScheduleFetchError('Schedule JSON is missing schedule.conference.days.') from exc

    sessions = []
    try:
        for day in days or []:
            rooms = day.get('rooms') or {}
            for room_name, talks in rooms.items():
                for talk in talks or []:
                    sessions.append(_session_from_talk(talk, room_name))
    except (AttributeError, TypeError) as exc:
        raise ScheduleFetchError('Schedule JSON days/rooms/talks have an unexpected shape.') from exc

    sessions.sort(key=lambda s: (s['start'] or '', s['room'] or '', s['title'] or ''))
    return sessions


def fetch_schedule_sessions(url: str) -> List[Dict[str, Any]]:
    """
    Returns the parsed sessions for a schedule export URL, using Django's cache for
    SCHEDULE_CACHE_SECONDS. Raises ScheduleFetchError on network, HTTP, or parse failures
    (failures are not cached, so the next request retries).
    """
    key = _cache_key(url)
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        response = requests.get(
            url,
            timeout=SCHEDULE_FETCH_TIMEOUT_SECONDS,
            headers={'User-Agent': settings.HARVEST_USER_AGENT, 'Accept': 'application/json'},
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ScheduleFetchError(f'Could not fetch schedule: {exc.__class__.__name__}') from exc

    sessions = parse_frab_schedule(data)
    cache.set(key, sessions, SCHEDULE_CACHE_SECONDS)
    return sessions
