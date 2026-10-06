"""
Wikimedia Commons harvester (`wikimedia_commons` quests).

Searches the File namespace for the event hashtag, then resolves each hit's uploader, upload
time, description page, categories, and description text (extmetadata ImageDescription and
ObjectName, HTML stripped) so the upload can be credited, checked against the quest's optional
category, and read by value-scoring quests (e.g. the year on a sidewalk stamp).
"""

import html
from typing import Any, Dict, List

from django.utils.html import strip_tags

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

PLATFORM = 'commons'
SEARCH_LIMIT = 50
MAX_CONTINUATIONS = 20


def parse_wikimedia_search_response(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Search hits as candidate files: {external_id (pageid), platform, external_url, title, snippet}."""
    results = []
    for item in (data.get('query') or {}).get('search') or []:
        title = item.get('title', '')
        results.append({
            'external_id': str(item.get('pageid')),
            'platform': PLATFORM,
            'external_url': f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
            'title': title,
            'snippet': item.get('snippet', ''),
        })
    return results


def search_commons_files(hashtag: str) -> List[Dict[str, Any]]:
    data = http_get(settings.WIKIMEDIA_COMMONS_API, 'Commons search', params={
        'action': 'query',
        'list': 'search',
        'srsearch': f"#{hashtag.lstrip('#')}",
        'srnamespace': '6',  # File namespace
        'srlimit': str(SEARCH_LIMIT),
        'srsort': 'create_timestamp_desc',
        'format': 'json',
    })
    return parse_wikimedia_search_response(data)


def _normalize_category(name: str) -> str:
    name = (name or '').strip()
    if name.lower().startswith('category:'):
        name = name[len('category:'):]
    return name.replace('_', ' ').strip().lower()


def _metadata_text(extmetadata: Dict[str, Any], name: str) -> str:
    """
    Plain text of one extmetadata field. Values are HTML, and a dict of language -> HTML when
    the API returns several languages.
    """
    value = ((extmetadata or {}).get(name) or {}).get('value') or ''
    if isinstance(value, dict):
        value = ' '.join(str(v) for v in value.values() if v)
    text = html.unescape(strip_tags(str(value)))
    return ' '.join(text.split())


def fetch_file_details(pageids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    pageid -> {title, user, timestamp, descriptionurl, url, categories, description,
    object_name} via prop=imageinfo|categories, following API continuation for long category
    lists.
    """
    details: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(pageids), 50):
        batch = pageids[start:start + 50]
        params = {
            'action': 'query',
            'pageids': '|'.join(batch),
            'prop': 'imageinfo|categories',
            'iiprop': 'user|timestamp|url|extmetadata',
            'iiextmetadatafilter': 'ImageDescription|ObjectName',
            'iiextmetadatalanguage': 'en',
            'cllimit': '50',
            'format': 'json',
        }
        cont: Dict[str, str] = {}
        for _ in range(MAX_CONTINUATIONS):
            data = http_get(settings.WIKIMEDIA_COMMONS_API, 'Commons file info',
                            params={**params, **cont})
            pages = (data.get('query') or {}).get('pages') or {}
            for pid, page in pages.items():
                entry = details.setdefault(str(pid), {
                    'title': page.get('title', ''),
                    'user': '', 'timestamp': '', 'descriptionurl': '', 'url': '',
                    'categories': [], 'description': '', 'object_name': '',
                })
                info = (page.get('imageinfo') or [None])[0]
                if info and not entry['user']:
                    entry.update({
                        'user': info.get('user', ''),
                        'timestamp': info.get('timestamp', ''),
                        'descriptionurl': info.get('descriptionurl', ''),
                        'url': info.get('url', ''),
                        'description': _metadata_text(info.get('extmetadata'), 'ImageDescription'),
                        'object_name': _metadata_text(info.get('extmetadata'), 'ObjectName'),
                    })
                for cat in page.get('categories') or []:
                    if cat.get('title') and cat['title'] not in entry['categories']:
                        entry['categories'].append(cat['title'])
            if 'continue' not in data:
                break
            cont = {k: str(v) for k, v in data['continue'].items()}
    return details


def harvest_commons(ctx: HarvestContext, quests: List[Quest]) -> None:
    event = ctx.event
    ctx.platform(PLATFORM)
    try:
        candidates = search_commons_files(event.hashtag)
        details = fetch_file_details([c['external_id'] for c in candidates]) if candidates else {}
    except HarvestError as exc:
        ctx.error(PLATFORM, str(exc))
        return

    for candidate in candidates:
        pageid = candidate['external_id']
        info = details.get(pageid)
        if not info or not info['user']:
            continue
        uploaded_at = parse_timestamp(info['timestamp'])
        file_categories = {_normalize_category(c) for c in info['categories']}

        for quest in quests:
            if not counts_for_quest(event, quest, uploaded_at):
                continue
            required_category = (quest.validation_rules or {}).get('category')
            if required_category and _normalize_category(required_category) not in file_categories:
                continue
            upsert_submission(
                ctx,
                platform=PLATFORM,
                quest=quest,
                external_id=f'{pageid}/q{quest.id}',
                external_url=info['descriptionurl'] or candidate['external_url'],
                author_username=info['user'],
                contributed_at=uploaded_at,
                element_count=1,
                diff_payload={
                    'media_type': 'image',
                    'pageid': pageid,
                    'title': info['title'] or candidate['title'],
                    'file_url': info['url'],
                    'categories': info['categories'],
                    'snippet': candidate['snippet'],
                    'description': info['description'],
                    'object_name': info['object_name'],
                },
            )
