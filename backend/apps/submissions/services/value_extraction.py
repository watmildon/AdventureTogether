"""
Value scoring: reading a number (usually a year) out of a submission, and the rule that turns
those numbers into points.

A quest opts in with `validation_rules.scoring`:

    "scoring": {
      "value": {"source": "description", "pattern": "\\b((?:18|19|20)\\d{2})\\b", "kind": "year"},
      "per_bucket": {"size": 10, "points": 5},
      "extreme_bonus": {"direction": "min", "points": 25}
    }

`value` says where the number comes from: "description" reads the submission's text fields
(a Commons file's description, object name and title; any other submission's diff_payload text),
"tag:<key>" reads that tag on every element in diff_payload.elements (OSM/OHM). The pattern's
first match that parses to a valid value wins (group 1 when the pattern has one, falling back
to the whole match). A "year" outside 1600..next year is not a value.

`per_bucket` and `extreme_bonus` are scored in services.progress; both are optional, and work
without `value` too when hosts enter the values themselves (verify with `extracted_value`).
"""

import html
import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Pattern

from django.utils import timezone
from django.utils.html import strip_tags

from apps.quests.models import Quest

KINDS = ('year', 'number')
DIRECTIONS = ('min', 'max')
MIN_YEAR = 1600
DEFAULT_PATTERNS = {
    'year': r'\b((?:16|17|18|19|20)\d{2})\b',
    'number': r'-?\d+(?:\.\d+)?',
}
# diff_payload text fields read by the "description" source, in this order: at the top level
# first, then in nested objects (e.g. an OSM changeset's comment, an OSM note's comments).
# Ids, usernames and timestamps are never read, so a changeset's created_at is not a "year".
DESCRIPTION_KEYS = ('description', 'caption', 'object_name', 'title', 'snippet', 'comment', 'text')


@dataclass(frozen=True)
class ScoringRule:
    """validation_rules.scoring, normalised. Missing parts are None / 0."""
    source: Optional[str]          # 'description', 'tag:<key>', or None (values entered by hosts)
    pattern: Optional[Pattern]
    kind: str                      # 'year' or 'number'
    bucket_size: Optional[float]   # None: no per-bucket points
    bucket_points: int
    direction: str                 # 'min' or 'max': the extreme_bonus direction (min when absent)
    bonus_points: Optional[int]    # None: no extreme bonus

    @property
    def has_bonus(self) -> bool:
        return self.bonus_points is not None

    def extreme(self, values: Iterable[float]) -> Optional[float]:
        values = list(values)
        if not values:
            return None
        return max(values) if self.direction == 'max' else min(values)

    def bucket(self, value: float):
        """Start of the bucket holding value, e.g. 1923 -> 1920 for decades."""
        start = math.floor(value / self.bucket_size) * self.bucket_size
        return int(start) if float(start).is_integer() else start


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def scoring_rule(quest: Quest) -> Optional[ScoringRule]:
    """The quest's scoring rule, or None when it has none. Invalid parts are dropped, not raised."""
    scoring = (quest.validation_rules or {}).get('scoring') if isinstance(quest.validation_rules, dict) else None
    if not isinstance(scoring, dict) or not scoring:
        return None

    value = scoring.get('value') if isinstance(scoring.get('value'), dict) else {}
    kind = value.get('kind') if value.get('kind') in KINDS else 'year'
    source = value.get('source')
    if not (source == 'description' or (isinstance(source, str) and source.startswith('tag:') and len(source) > 4)):
        source = None
    pattern = None
    if source:
        try:
            pattern = re.compile(value.get('pattern') or DEFAULT_PATTERNS[kind])
        except (re.error, TypeError):
            source = None

    per_bucket = scoring.get('per_bucket') if isinstance(scoring.get('per_bucket'), dict) else {}
    bucket_size = _number(per_bucket.get('size'))
    if bucket_size is None or bucket_size <= 0:
        bucket_size = None
    bonus = scoring.get('extreme_bonus') if isinstance(scoring.get('extreme_bonus'), dict) else None
    direction = (bonus or {}).get('direction')

    return ScoringRule(
        source=source,
        pattern=pattern,
        kind=kind,
        bucket_size=bucket_size,
        bucket_points=int(_number(per_bucket.get('points')) or 0) if bucket_size else 0,
        direction=direction if direction in DIRECTIONS else 'min',
        bonus_points=int(_number(bonus.get('points')) or 0) if bonus is not None else None,
    )


def validate_scoring(scoring: Any) -> List[str]:
    """Problems with a validation_rules.scoring block, as messages for the quest serializer."""
    if scoring is None:
        return []
    if not isinstance(scoring, dict):
        return ['scoring must be a JSON object.']
    errors = []
    value = scoring.get('value')
    if value is not None:
        if not isinstance(value, dict):
            errors.append('scoring.value must be a JSON object.')
        else:
            source = value.get('source')
            if not (source == 'description' or (isinstance(source, str) and source.startswith('tag:') and len(source) > 4)):
                errors.append('scoring.value.source must be "description" or "tag:<key>".')
            if value.get('kind', 'year') not in KINDS:
                errors.append('scoring.value.kind must be "year" or "number".')
            if value.get('pattern'):
                try:
                    re.compile(value['pattern'])
                except (re.error, TypeError):
                    errors.append('scoring.value.pattern is not a valid regular expression.')
    per_bucket = scoring.get('per_bucket')
    if per_bucket is not None:
        size = _number(per_bucket.get('size')) if isinstance(per_bucket, dict) else None
        if size is None or size <= 0 or _number(per_bucket.get('points')) is None:
            errors.append('scoring.per_bucket needs a positive "size" and a number of "points".')
    bonus = scoring.get('extreme_bonus')
    if bonus is not None:
        if not isinstance(bonus, dict) or bonus.get('direction', 'min') not in DIRECTIONS \
                or _number(bonus.get('points')) is None:
            errors.append('scoring.extreme_bonus needs "direction" ("min" or "max") and a number of "points".')
    return errors


# --- Extraction -------------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    return html.unescape(strip_tags(text))


def _description_texts(payload: Dict[str, Any]) -> List[str]:
    """The DESCRIPTION_KEYS text of a diff_payload: top level first, then nested objects (not elements)."""
    texts = [payload[key] for key in DESCRIPTION_KEYS if isinstance(payload.get(key), str)]
    for key, value in payload.items():
        if key == 'elements':
            continue
        nested = value if isinstance(value, list) else [value]
        for node in nested:
            if isinstance(node, dict):
                texts += [node[k] for k in DESCRIPTION_KEYS if isinstance(node.get(k), str)]
    return [_clean_text(t) for t in texts if t]


def parse_value(rule: ScoringRule, text: str) -> Optional[float]:
    """The first match of the rule's pattern in text that is a valid value of the rule's kind."""
    if not text or rule.pattern is None:
        return None
    max_year = timezone.now().year + 1
    for match in rule.pattern.finditer(text):
        candidates = [match.group(1), match.group(0)] if match.re.groups else [match.group(0)]
        for candidate in candidates:
            number = _number((candidate or '').replace(',', '').strip())
            if number is None:
                continue
            if rule.kind == 'year' and not (number.is_integer() and MIN_YEAR <= number <= max_year):
                continue
            return number
    return None


def extract_values(quest: Quest, submission_like: Any) -> List[float]:
    """
    Values found in a Submission (or anything with a diff_payload attribute or key) for the
    quest's scoring.value: at most one from the description text, or one per element for a
    tag source. Empty when the quest has no scoring.value.
    """
    rule = scoring_rule(quest)
    if rule is None or rule.source is None:
        return []
    if isinstance(submission_like, dict):
        payload = submission_like.get('diff_payload', submission_like)
    else:
        payload = getattr(submission_like, 'diff_payload', None)
    if not isinstance(payload, dict):
        return []

    if rule.source == 'description':
        for text in _description_texts(payload):
            value = parse_value(rule, text)
            if value is not None:
                return [value]
        return []

    key = rule.source[len('tag:'):]
    values = []
    for element in payload.get('elements') or []:
        tag = ((element or {}).get('tags') or {}).get(key) if isinstance(element, dict) else None
        value = parse_value(rule, str(tag)) if tag is not None else None
        if value is not None:
            values.append(value)
    return values


def apply_extraction(quest: Quest, submission) -> bool:
    """
    Fills submission.extracted_value (the extreme per the rule's direction) and
    diff_payload['extracted_values'] (every value found) from the submission's diff_payload.
    Does not save. A value a host has set (diff_payload['value_overridden_by']) is kept.
    Returns whether anything changed; a no-op when the quest has no scoring.value.
    """
    rule = scoring_rule(quest)
    if rule is None or rule.source is None:
        return False
    payload = submission.diff_payload if isinstance(submission.diff_payload, dict) else {}
    if payload.get('value_overridden_by'):
        return False
    values = extract_values(quest, submission)
    representative = rule.extreme(values)
    if payload.get('extracted_values') == values and submission.extracted_value == representative:
        return False
    submission.diff_payload = {**payload, 'extracted_values': values}
    submission.extracted_value = representative
    return True


def override_value(submission, value: Optional[float], by: str) -> None:
    """A host's correction: the submission's only value becomes `value` (None clears it). Does not save."""
    payload = submission.diff_payload if isinstance(submission.diff_payload, dict) else {}
    submission.extracted_value = value
    submission.diff_payload = {
        **payload,
        'extracted_values': [] if value is None else [value],
        'value_overridden_by': by or 'Host',
    }


def submission_values(submission) -> List[float]:
    """
    Every value a submission contributes to scoring: the per-element values when they are
    consistent with extracted_value, otherwise extracted_value alone (e.g. set through the API).
    """
    if submission.extracted_value is None:
        return []
    payload = submission.diff_payload if isinstance(submission.diff_payload, dict) else {}
    stored = payload.get('extracted_values')
    if isinstance(stored, list):
        values = [v for v in (_number(x) for x in stored) if v is not None]
        if submission.extracted_value in values:
            return values
    return [submission.extracted_value]
