/**
 * Builds a quest's `validation_rules` from the host builder's form, following the
 * per-type contract the backend matchers read (see documentation/api_reference.md):
 *
 *   osm_tags           {required_tags, target_count, require_hashtag, radius_m (point targets only),
 *                       action (only when not "any")}
 *   wikimedia_commons  {category?, target_count}
 *   wikidata_entry     {target_count}
 *   wikidata_statement {qid, properties, target_count}
 *   osm_notes          {target_count}
 *   ohm_feature        {required_tags, target_count}
 *   oss_contribution   {kinds, allowed_owners?, target_count}
 *   location_checkin   {radius_m, min_minutes}
 *   street_imagery     {target_count}
 *   mangrove_review    {target_count, require_hashtag, min_opinion_chars}
 *   maproulette_task   {target_count, statuses, require_hashtag, challenge_ids?}
 *
 * Any type can also carry an optional `scoring` block (value scoring: points per distinct
 * bucket of values and a bonus for the extreme value; see documentation/quest_types.md):
 *
 *   scoring {value?: {source: "description" | "tag:<key>", pattern?, kind: "year" | "number"},
 *            per_bucket?: {size, points}, extreme_bonus?: {direction: "min" | "max", points}}
 *
 * rulesToForm is the inverse, used when the builder edits an existing quest.
 * Kept free of Vue so it can be unit-tested directly.
 */

import type { CriteriaType } from '../api'

/** Which osm_tags edits count: added or updated, newly created elements, or updates only. */
export type OsmAction = 'any' | 'create' | 'modify'
const OSM_ACTIONS: OsmAction[] = ['any', 'create', 'modify']

/** Where a value-scoring quest reads its value; 'none' means hosts enter values when verifying. */
export type ScoringSource = 'description' | 'tag' | 'none'
export type ScoringKind = 'year' | 'number'

/** The backend's default patterns (services/value_extraction.py), used when the form's is blank. */
export const DEFAULT_SCORING_PATTERNS: Record<ScoringKind, string> = {
  year: '\\b((?:16|17|18|19|20)\\d{2})\\b',
  number: '-?\\d+(?:\\.\\d+)?'
}

export interface ScoringForm {
  enabled: boolean
  source: ScoringSource
  /** Tag read on each element when source is 'tag', e.g. "start_date". */
  tagKey: string
  kind: ScoringKind
  /** Regex whose first valid match is the value; blank uses DEFAULT_SCORING_PATTERNS[kind]. */
  pattern: string
  bucketEnabled: boolean
  bucketSize: number
  bucketPoints: number
  bonusEnabled: boolean
  bonusDirection: 'min' | 'max'
  bonusPoints: number
}

/** Value scoring off, with the sidewalk-stamp values ready for when it is switched on. */
export function defaultScoringForm(): ScoringForm {
  return {
    enabled: false,
    source: 'description',
    tagKey: 'start_date',
    kind: 'year',
    pattern: DEFAULT_SCORING_PATTERNS.year,
    bucketEnabled: true,
    bucketSize: 10,
    bucketPoints: 5,
    bonusEnabled: true,
    bonusDirection: 'min',
    bonusPoints: 25
  }
}

/**
 * The pattern to show after the kind changes: a pattern still at the old kind's default (or
 * blank) follows the new kind; one the host wrote is kept.
 */
export function patternForKind(pattern: string, from: ScoringKind, to: ScoringKind): string {
  return !pattern.trim() || pattern === DEFAULT_SCORING_PATTERNS[from] ? DEFAULT_SCORING_PATTERNS[to] : pattern
}

/** MapRoulette task statuses the builder offers (fixed, already fixed, false positive). */
export const MAPROULETTE_STATUSES = { fixed: 1, alreadyFixed: 5, falsePositive: 2 } as const
export type MapRouletteStatusKey = keyof typeof MAPROULETTE_STATUSES

export interface TagRow {
  key: string
  /** A literal value, or "*" (or blank) for "any value". */
  value: string
}

export interface RuleForm {
  osmTags: TagRow[]
  ohmTags: TagRow[]
  targetCount: number
  /** Matching radius around a point target for osm_tags. */
  osmRadiusM: number
  requireHashtag: boolean
  /** osm_tags `action`; 'any' is the backend default and is left out of the rules. */
  osmAction: OsmAction
  category: string
  qid: string
  /** Comma- or space-separated property ids, e.g. "P84, P571". */
  properties: string
  kinds: { pr: boolean; issue: boolean }
  /** Comma- or space-separated GitHub owners/orgs, e.g. "OSGeo, qgis". */
  allowedOwners: string
  checkinRadiusM: number
  minMinutes: number
  /** mangrove_review: minimum review length (0 = any). The hashtag rule uses requireHashtag. */
  minOpinionChars: number
  /** maproulette_task statuses that count. */
  mrStatuses: Record<MapRouletteStatusKey, boolean>
  /** Comma- or space-separated MapRoulette challenge ids (blank = any challenge). */
  challengeIds: string
  /** maproulette_task require_hashtag; off by default since MapRoulette edits rarely carry it. */
  mrRequireHashtag: boolean
  /** validation_rules.scoring, for every type. */
  scoring: ScoringForm
}

/** Fresh form values with the contract's defaults. */
export function defaultRuleForm(): RuleForm {
  return {
    osmTags: [
      { key: 'amenity', value: 'restaurant' },
      { key: 'opening_hours', value: '*' }
    ],
    ohmTags: [{ key: 'start_date', value: '*' }],
    targetCount: 1,
    osmRadiusM: 300,
    requireHashtag: true,
    osmAction: 'any',
    category: '',
    qid: '',
    properties: '',
    kinds: { pr: true, issue: true },
    allowedOwners: '',
    checkinRadiusM: 50,
    minMinutes: 0,
    minOpinionChars: 0,
    mrStatuses: { fixed: true, alreadyFixed: true, falsePositive: false },
    challengeIds: '',
    mrRequireHashtag: false,
    scoring: defaultScoringForm()
  }
}

/** Splits "P84, P571 P31" into ["P84", "P571", "P31"]. */
export function splitList(text: string): string[] {
  return text.split(/[\s,]+/).map((item) => item.trim()).filter(Boolean)
}

/** Tag rows to {key: value}; blank values mean "any value" ("*"); blank keys are dropped. */
export function tagsToObject(rows: TagRow[]): Record<string, string> {
  const tags: Record<string, string> = {}
  rows.forEach(({ key, value }) => {
    const k = key.trim()
    if (k) tags[k] = value.trim() || '*'
  })
  return tags
}

const positiveInt = (value: number, fallback: number) =>
  Number.isFinite(value) && value >= 1 ? Math.round(value) : fallback
const intOr = (value: number, fallback: number) => (Number.isFinite(value) ? Math.round(value) : fallback)

/** The `scoring` block for the form, or null when value scoring is off. */
export function composeScoring(form: ScoringForm): Record<string, any> | null {
  if (!form.enabled) return null
  const scoring: Record<string, any> = {}
  if (form.source !== 'none') {
    scoring.value = {
      source: form.source === 'tag' ? `tag:${form.tagKey.trim()}` : 'description',
      ...(form.pattern.trim() ? { pattern: form.pattern } : {}),
      kind: form.kind
    }
  }
  if (form.bucketEnabled) {
    const size = Number.isFinite(form.bucketSize) && form.bucketSize > 0 ? form.bucketSize : 10
    scoring.per_bucket = { size, points: intOr(form.bucketPoints, 0) }
  }
  if (form.bonusEnabled) {
    scoring.extreme_bonus = { direction: form.bonusDirection, points: intOr(form.bonusPoints, 0) }
  }
  return scoring
}

/** validation_rules for the form: the type's own keys plus `scoring` when value scoring is on. */
export function composeValidationRules(
  type: CriteriaType,
  form: RuleForm,
  hasPointTarget: boolean
): Record<string, any> {
  const rules = composeTypeRules(type, form, hasPointTarget)
  const scoring = composeScoring(form.scoring)
  return scoring ? { ...rules, scoring } : rules
}

function composeTypeRules(type: CriteriaType, form: RuleForm, hasPointTarget: boolean): Record<string, any> {
  const target_count = positiveInt(form.targetCount, 1)

  switch (type) {
    case 'osm_tags':
      return {
        required_tags: tagsToObject(form.osmTags),
        target_count,
        require_hashtag: form.requireHashtag,
        // The radius only means something around a point target
        ...(hasPointTarget ? { radius_m: positiveInt(form.osmRadiusM, 300) } : {}),
        ...(form.osmAction !== 'any' ? { action: form.osmAction } : {})
      }
    case 'wikimedia_commons':
      return form.category.trim() ? { category: form.category.trim(), target_count } : { target_count }
    case 'wikidata_statement':
      return {
        qid: form.qid.trim().toUpperCase(),
        properties: splitList(form.properties).map((p) => p.toUpperCase()),
        target_count
      }
    case 'ohm_feature':
      return { required_tags: tagsToObject(form.ohmTags), target_count }
    case 'oss_contribution': {
      const kinds = (['pr', 'issue'] as const).filter((kind) => form.kinds[kind])
      const owners = splitList(form.allowedOwners)
      return owners.length ? { kinds, allowed_owners: owners, target_count } : { kinds, target_count }
    }
    case 'location_checkin':
      return {
        radius_m: positiveInt(form.checkinRadiusM, 50),
        min_minutes: Number.isFinite(form.minMinutes) && form.minMinutes > 0 ? Math.round(form.minMinutes) : 0
      }
    case 'mangrove_review':
      return {
        target_count,
        require_hashtag: form.requireHashtag,
        min_opinion_chars: Number.isFinite(form.minOpinionChars) && form.minOpinionChars > 0 ? Math.round(form.minOpinionChars) : 0
      }
    case 'maproulette_task': {
      const statuses = (Object.keys(MAPROULETTE_STATUSES) as MapRouletteStatusKey[])
        .filter((key) => form.mrStatuses[key])
        .map((key) => MAPROULETTE_STATUSES[key])
        .sort((a, b) => a - b)
      const challengeIds = splitList(form.challengeIds).map(Number).filter((id) => Number.isInteger(id) && id > 0)
      return {
        target_count,
        statuses,
        require_hashtag: form.mrRequireHashtag,
        ...(challengeIds.length ? { challenge_ids: challengeIds } : {})
      }
    }
    case 'wikidata_entry':
    case 'osm_notes':
    case 'street_imagery':
    default:
      return { target_count }
  }
}

/**
 * The validation_rules keys the builder form models, per type (every type models `scoring`).
 * Anything else is kept as is on edit.
 */
export const MODELLED_RULE_KEYS: Record<CriteriaType, string[]> = {
  osm_tags: ['required_tags', 'target_count', 'require_hashtag', 'radius_m', 'action', 'scoring'],
  wikimedia_commons: ['category', 'target_count', 'scoring'],
  wikidata_entry: ['target_count', 'scoring'],
  wikidata_statement: ['qid', 'properties', 'target_count', 'scoring'],
  osm_notes: ['target_count', 'scoring'],
  ohm_feature: ['required_tags', 'target_count', 'scoring'],
  oss_contribution: ['kinds', 'allowed_owners', 'target_count', 'scoring'],
  location_checkin: ['radius_m', 'min_minutes', 'scoring'],
  street_imagery: ['target_count', 'scoring'],
  mangrove_review: ['target_count', 'require_hashtag', 'min_opinion_chars', 'scoring'],
  maproulette_task: ['target_count', 'statuses', 'require_hashtag', 'challenge_ids', 'scoring']
}

/** {key: value} to tag rows (the inverse of tagsToObject). */
export function objectToTags(tags: unknown): TagRow[] {
  if (!tags || typeof tags !== 'object') return []
  return Object.entries(tags as Record<string, unknown>).map(([key, value]) => ({
    key,
    value: value == null ? '*' : String(value)
  }))
}

const listText = (value: unknown) => (Array.isArray(value) ? value.join(', ') : typeof value === 'string' ? value : '')
const numberOr = (value: unknown, fallback: number) => {
  const n = Number(value)
  return value !== null && value !== undefined && value !== '' && Number.isFinite(n) ? n : fallback
}

/** The inverse of composeScoring: a quest's `scoring` block (or none) as the form. */
export function scoringToForm(scoring: unknown): ScoringForm {
  const form = defaultScoringForm()
  if (!scoring || typeof scoring !== 'object') return form
  const s = scoring as Record<string, any>
  form.enabled = true

  const value = s.value && typeof s.value === 'object' ? s.value : null
  if (!value) {
    form.source = 'none'
  } else if (typeof value.source === 'string' && value.source.startsWith('tag:')) {
    form.source = 'tag'
    form.tagKey = value.source.slice(4)
  } else {
    form.source = 'description'
  }
  form.kind = value?.kind === 'number' ? 'number' : 'year'
  // Blank means "the backend default", so a rule without a pattern stays without one
  form.pattern = value ? (typeof value.pattern === 'string' ? value.pattern : '') : DEFAULT_SCORING_PATTERNS[form.kind]

  form.bucketEnabled = Boolean(s.per_bucket && typeof s.per_bucket === 'object')
  if (form.bucketEnabled) {
    form.bucketSize = numberOr(s.per_bucket.size, form.bucketSize)
    form.bucketPoints = numberOr(s.per_bucket.points, form.bucketPoints)
  }
  form.bonusEnabled = Boolean(s.extreme_bonus && typeof s.extreme_bonus === 'object')
  if (form.bonusEnabled) {
    form.bonusDirection = s.extreme_bonus.direction === 'max' ? 'max' : 'min'
    form.bonusPoints = numberOr(s.extreme_bonus.points, form.bonusPoints)
  }
  return form
}

/**
 * The inverse of composeValidationRules: decomposes a quest's validation_rules into the
 * builder form so an existing quest can be edited. Keys the type does not use, and missing
 * keys, fall back to defaultRuleForm(), so composing the result reproduces the rules.
 */
export function rulesToForm(type: CriteriaType, rules: Record<string, any> | null | undefined): RuleForm {
  const form = defaultRuleForm()
  const r = rules && typeof rules === 'object' ? rules : {}
  form.targetCount = numberOr(r.target_count, form.targetCount)
  form.scoring = scoringToForm(r.scoring)

  switch (type) {
    case 'osm_tags':
      form.osmTags = objectToTags(r.required_tags)
      form.requireHashtag = r.require_hashtag !== false
      form.osmRadiusM = numberOr(r.radius_m, form.osmRadiusM)
      // Unknown actions are treated as 'any' by the harvester
      form.osmAction = OSM_ACTIONS.includes(r.action) ? r.action : 'any'
      break
    case 'ohm_feature':
      form.ohmTags = objectToTags(r.required_tags)
      break
    case 'wikimedia_commons':
      form.category = typeof r.category === 'string' ? r.category : ''
      break
    case 'wikidata_statement':
      form.qid = typeof r.qid === 'string' ? r.qid : ''
      form.properties = listText(r.properties)
      break
    case 'oss_contribution': {
      // The harvester treats missing/empty kinds as both
      const kinds: string[] = Array.isArray(r.kinds) && r.kinds.length ? r.kinds : ['pr', 'issue']
      form.kinds = { pr: kinds.includes('pr'), issue: kinds.includes('issue') }
      form.allowedOwners = listText(r.allowed_owners)
      break
    }
    case 'location_checkin':
      form.checkinRadiusM = numberOr(r.radius_m, form.checkinRadiusM)
      form.minMinutes = numberOr(r.min_minutes, form.minMinutes)
      break
    case 'mangrove_review':
      form.requireHashtag = r.require_hashtag !== false
      form.minOpinionChars = numberOr(r.min_opinion_chars, form.minOpinionChars)
      break
    case 'maproulette_task': {
      // The harvester treats missing/empty statuses as fixed and already fixed
      const statuses: number[] = Array.isArray(r.statuses) && r.statuses.length ? r.statuses.map(Number) : [1, 5]
      form.mrStatuses = {
        fixed: statuses.includes(MAPROULETTE_STATUSES.fixed),
        alreadyFixed: statuses.includes(MAPROULETTE_STATUSES.alreadyFixed),
        falsePositive: statuses.includes(MAPROULETTE_STATUSES.falsePositive)
      }
      form.challengeIds = listText(r.challenge_ids)
      form.mrRequireHashtag = r.require_hashtag === true
      break
    }
  }
  return form
}

/** validation_rules entries the form does not model for this type (preserved when saving an edit). */
export function unmodelledRules(type: CriteriaType, rules: Record<string, any> | null | undefined): Record<string, any> {
  const known = new Set(MODELLED_RULE_KEYS[type] || [])
  return Object.fromEntries(Object.entries(rules || {}).filter(([key]) => !known.has(key)))
}

/** A human-readable problem with the value-scoring inputs, or null when they are usable (or off). */
export function validateScoringForm(form: ScoringForm): string | null {
  if (!form.enabled) return null
  if (form.source === 'tag' && !form.tagKey.trim()) return 'Value scoring: enter the OSM tag to read, e.g. start_date.'
  if (!form.bucketEnabled && !form.bonusEnabled) return 'Value scoring: turn on points per bucket, the bonus, or both.'
  if (form.bucketEnabled && !(Number.isFinite(form.bucketSize) && form.bucketSize > 0)) {
    return 'Value scoring: the bucket size must be more than 0 (10 for decades).'
  }
  return null
}

/** Returns a human-readable problem with the rules for this type, or null when they are usable. */
export function validateRuleForm(type: CriteriaType, form: RuleForm, hasPointTarget: boolean): string | null {
  const typeProblem = validateTypeRules(type, form, hasPointTarget)
  return typeProblem ?? validateScoringForm(form.scoring)
}

function validateTypeRules(type: CriteriaType, form: RuleForm, hasPointTarget: boolean): string | null {
  switch (type) {
    case 'osm_tags':
      return Object.keys(tagsToObject(form.osmTags)).length ? null : 'Add at least one required OSM tag.'
    case 'ohm_feature':
      return Object.keys(tagsToObject(form.ohmTags)).length ? null : 'Add at least one required OHM tag.'
    case 'wikidata_statement': {
      if (!/^Q\d+$/i.test(form.qid.trim())) return 'Enter the Wikidata item id, e.g. Q111393295.'
      const props = splitList(form.properties)
      if (!props.length || props.some((p) => !/^P\d+$/i.test(p))) return 'Enter property ids such as P84, P571.'
      return null
    }
    case 'oss_contribution':
      return form.kinds.pr || form.kinds.issue ? null : 'Pick pull requests, issues, or both.'
    case 'location_checkin':
      return hasPointTarget ? null : 'Check-in quests need a target point: click the map where people should stand.'
    case 'maproulette_task': {
      if (!Object.values(form.mrStatuses).some(Boolean)) return 'Pick at least one task status that counts.'
      const ids = splitList(form.challengeIds)
      return ids.every((id) => /^\d+$/.test(id)) ? null : 'Challenge ids are numbers, e.g. 56424, 42871.'
    }
    default:
      return null
  }
}
