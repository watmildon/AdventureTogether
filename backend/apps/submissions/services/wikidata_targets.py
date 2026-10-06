"""
Targets of `wikidata_area` quests: the Wikidata items inside the quest area that still lack the
quest's properties (usually P18, an image), so participants know which items to photograph.

One SPARQL query against the Wikidata Query Service (`WIKIDATA_SPARQL`) finds items with
coordinates (P625) in the quest's bounding box (`wikibase:box`) that have none of the
properties; the rows are then filtered with point_in_quest_area, since a box is wider than a
polygon or radius. Results are cached for TARGETS_CACHE_SECONDS per quest and rules.
"""

import hashlib
import json
from typing import Any, Dict, List

from django.conf import settings
from django.core.cache import cache

from apps.quests.models import Quest
from .harvest_common import http_get, point_in_quest_area, quest_bbox
from .wikidata_harvester import area_properties

# The query service is slow-ish and the answer changes only as items gain photos.
TARGETS_CACHE_SECONDS = 30 * 60
SPARQL_TIMEOUT = 60
SPARQL_LIMIT = 500
ENTITY_PREFIX = 'http://www.wikidata.org/entity/'


def build_targets_query(bbox, properties: List[str]) -> str:
    """
    SPARQL for items with P625 inside (min_lon, min_lat, max_lon, max_lat) lacking every one
    of `properties` (ids already validated as P<digits> by area_properties), with English labels.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    missing = '\n'.join(f'  FILTER NOT EXISTS {{ ?item wdt:{pid} [] }}' for pid in properties)
    return f'''SELECT ?item ?itemLabel ?lat ?lon WHERE {{
  SERVICE wikibase:box {{
    ?item wdt:P625 ?location .
    bd:serviceParam wikibase:cornerSouthWest "Point({min_lon:.6f} {min_lat:.6f})"^^geo:wktLiteral .
    bd:serviceParam wikibase:cornerNorthEast "Point({max_lon:.6f} {max_lat:.6f})"^^geo:wktLiteral .
  }}
{missing}
  BIND(geof:latitude(?location) AS ?lat)
  BIND(geof:longitude(?location) AS ?lon)
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT {SPARQL_LIMIT}'''


def parse_targets_response(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """SPARQL JSON results as [{qid, label, lat, lon}], one row per item (the first coordinate)."""
    targets: Dict[str, Dict[str, Any]] = {}
    for row in (data.get('results') or {}).get('bindings') or []:
        uri = (row.get('item') or {}).get('value', '')
        if not uri.startswith(ENTITY_PREFIX):
            continue
        qid = uri[len(ENTITY_PREFIX):]
        try:
            lat = float(row['lat']['value'])
            lon = float(row['lon']['value'])
        except (KeyError, TypeError, ValueError):
            continue
        targets.setdefault(qid, {
            'qid': qid,
            'label': (row.get('itemLabel') or {}).get('value') or qid,
            'lat': lat,
            'lon': lon,
        })
    return list(targets.values())


def _cache_key(quest: Quest, bbox) -> str:
    # Rules and area both shape the answer; hash them so any edit to the quest misses the cache.
    geometry = quest.target_geometry.wkt if quest.target_geometry is not None else None
    blob = json.dumps({'rules': quest.validation_rules or {}, 'bbox': bbox, 'geometry': geometry},
                      sort_keys=True, default=str)
    return f'wikidata-targets:{quest.id}:' + hashlib.sha256(blob.encode('utf-8')).hexdigest()


def wikidata_area_targets(quest: Quest) -> List[Dict[str, Any]]:
    """
    The quest's target items, sorted by label: [{qid, label, lat, lon, wikidata_url,
    wikishootme_url}]. Raises HarvestError when the query service fails (failures are not cached).
    """
    bbox = tuple(quest_bbox(quest.event, quest))
    key = _cache_key(quest, bbox)
    cached = cache.get(key)
    if cached is not None:
        return cached

    data = http_get(
        settings.WIKIDATA_SPARQL,
        'Wikidata query',
        params={'query': build_targets_query(bbox, area_properties(quest)), 'format': 'json'},
        headers={'Accept': 'application/sparql-results+json'},
        timeout=SPARQL_TIMEOUT,
    )
    targets = []
    for item in parse_targets_response(data):
        if not point_in_quest_area(quest.event, quest, item['lat'], item['lon']):
            continue
        targets.append({
            **item,
            'wikidata_url': f"https://www.wikidata.org/wiki/{item['qid']}",
            'wikishootme_url': f"https://wikishootme.toolforge.org/#lat={item['lat']}&lng={item['lon']}&zoom=18",
        })
    targets.sort(key=lambda t: (t['label'].lower(), t['qid']))
    cache.set(key, targets, TARGETS_CACHE_SECONDS)
    return targets
