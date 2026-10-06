"""
Conference schedule import (pretalx / frab JSON export).

Hosts can point an event at a schedule export so quests can be linked to the sessions that
inspired them. The export is parsed into a flat list of sessions whose shape matches
Quest.inspired_by, so a client can copy a session straight into a quest.
"""

import hashlib
import ipaddress
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlsplit

import requests
from django.conf import settings
from django.core.cache import cache

# Schedules change rarely during a conference; 10 minutes keeps the picker responsive
# without hammering the schedule host.
SCHEDULE_CACHE_SECONDS = 10 * 60
SCHEDULE_FETCH_TIMEOUT_SECONDS = 15
# Redirects are followed by hand so every hop is checked against the host allowlist.
SCHEDULE_MAX_REDIRECTS = 5


class ScheduleFetchError(Exception):
    """Raised when a schedule export cannot be downloaded or parsed."""


def schedule_url_error(url: str) -> Optional[str]:
    """
    Returns why the server must not fetch `url`, or None when it may.

    Event.schedule_url is client-writable, so only https URLs whose hostname equals, or is a
    subdomain of, an entry in settings.SCHEDULE_URL_ALLOWED_HOSTS are fetched. IP literals are
    always refused, which keeps loopback, private and link-local addresses out of reach.
    """
    allowed = [h.strip().lower().rstrip('.') for h in settings.SCHEDULE_URL_ALLOWED_HOSTS if h.strip()]
    try:
        parts = urlsplit(url or '')
        host = (parts.hostname or '').rstrip('.')
    except ValueError:
        return 'Schedule URL is not a valid URL.'
    if parts.scheme.lower() != 'https':
        return 'Schedule URL must use https.'
    if not host:
        return 'Schedule URL has no host.'
    try:
        ipaddress.ip_address(host)
        return 'Schedule URL must use a host name, not an IP address.'
    except ValueError:
        pass
    if not any(host == a or host.endswith('.' + a) for a in allowed):
        listed = ', '.join(allowed) or '(none configured)'
        return f'Schedule URL host "{host}" is not allowed. Allowed hosts (and their subdomains): {listed}.'
    return None


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
    SCHEDULE_CACHE_SECONDS. Raises ScheduleFetchError when the URL (or a redirect target) is not
    on the host allowlist, and on network, HTTP, or parse failures (failures are not cached, so
    the next request retries).
    """
    error = schedule_url_error(url)
    if error:
        raise ScheduleFetchError(error)

    key = _cache_key(url)
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        target = url
        for _ in range(SCHEDULE_MAX_REDIRECTS + 1):
            response = requests.get(
                target,
                timeout=SCHEDULE_FETCH_TIMEOUT_SECONDS,
                headers={'User-Agent': settings.HARVEST_USER_AGENT, 'Accept': 'application/json'},
                allow_redirects=False,
            )
            if not 300 <= response.status_code < 400:
                break
            target = urljoin(target, response.headers.get('Location') or '')
            error = schedule_url_error(target)
            if error:
                raise ScheduleFetchError(f'Schedule redirect refused: {error}')
        else:
            raise ScheduleFetchError('Could not fetch schedule: too many redirects')
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ScheduleFetchError(f'Could not fetch schedule: {exc.__class__.__name__}') from exc

    sessions = parse_frab_schedule(data)
    cache.set(key, sessions, SCHEDULE_CACHE_SECONDS)
    return sessions
