/**
 * Builds a quest's `validation_rules` from the host builder's form, following the
 * per-type contract the backend matchers read (see documentation/api_reference.md):
 *
 *   osm_tags           {required_tags, target_count, require_hashtag, radius_m (point targets only)}
 *   wikimedia_commons  {category?, target_count}
 *   wikidata_entry     {target_count}
 *   wikidata_statement {qid, properties, target_count}
 *   osm_notes          {target_count}
 *   ohm_feature        {required_tags, target_count}
 *   oss_contribution   {kinds, allowed_owners?, target_count}
 *   location_checkin   {radius_m, min_minutes}
 *   street_imagery     {target_count}
 *
 * Kept free of Vue so it can be unit-tested directly.
 */

import type { CriteriaType } from '../api'

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
  category: string
  qid: string
  /** Comma- or space-separated property ids, e.g. "P84, P571". */
  properties: string
  kinds: { pr: boolean; issue: boolean }
  /** Comma- or space-separated GitHub owners/orgs, e.g. "OSGeo, qgis". */
  allowedOwners: string
  checkinRadiusM: number
  minMinutes: number
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
    category: '',
    qid: '',
    properties: '',
    kinds: { pr: true, issue: true },
    allowedOwners: '',
    checkinRadiusM: 50,
    minMinutes: 0
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

export function composeValidationRules(
  type: CriteriaType,
  form: RuleForm,
  hasPointTarget: boolean
): Record<string, any> {
  const target_count = positiveInt(form.targetCount, 1)

  switch (type) {
    case 'osm_tags':
      return {
        required_tags: tagsToObject(form.osmTags),
        target_count,
        require_hashtag: form.requireHashtag,
        // The radius only means something around a point target
        ...(hasPointTarget ? { radius_m: positiveInt(form.osmRadiusM, 300) } : {})
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
    case 'wikidata_entry':
    case 'osm_notes':
    case 'street_imagery':
    default:
      return { target_count }
  }
}

/** Returns a human-readable problem with the rules for this type, or null when they are usable. */
export function validateRuleForm(type: CriteriaType, form: RuleForm, hasPointTarget: boolean): string | null {
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
    default:
      return null
  }
}
