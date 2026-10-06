import { describe, it, expect } from 'vitest'
import {
  composeValidationRules,
  defaultRuleForm,
  validateRuleForm,
  tagsToObject,
  splitList,
  rulesToForm,
  unmodelledRules,
  objectToTags,
  composeScoring,
  scoringToForm,
  defaultScoringForm,
  patternForKind,
  DEFAULT_SCORING_PATTERNS
} from '../questRules'
import type { CriteriaType } from '../../api'
import { CRITERIA_TYPES } from '../useQuestTypes'

describe('composeValidationRules', () => {
  it('osm_tags: tags, target_count and hashtag, radius only with a point target', () => {
    const form = { ...defaultRuleForm(), targetCount: 5 }
    expect(composeValidationRules('osm_tags', form, true)).toEqual({
      required_tags: { amenity: 'restaurant', opening_hours: '*' },
      target_count: 5,
      require_hashtag: true,
      radius_m: 300
    })
    expect(composeValidationRules('osm_tags', form, false)).not.toHaveProperty('radius_m')
    expect(composeValidationRules('osm_tags', form, false)).not.toHaveProperty('action')
  })

  it('osm_tags: action only when it is not the default "any"', () => {
    const form = { ...defaultRuleForm(), osmAction: 'create' as const }
    expect(composeValidationRules('osm_tags', form, false)).toEqual({
      required_tags: { amenity: 'restaurant', opening_hours: '*' },
      target_count: 1,
      require_hashtag: true,
      action: 'create'
    })
    expect(composeValidationRules('osm_tags', { ...form, osmAction: 'modify' }, false).action).toBe('modify')
    // ohm_feature does not model it
    expect(composeValidationRules('ohm_feature', form, false)).not.toHaveProperty('action')
  })

  it('wikimedia_commons: category only when given', () => {
    const form = defaultRuleForm()
    expect(composeValidationRules('wikimedia_commons', form, false)).toEqual({ target_count: 1 })
    form.category = ' Sacramento '
    expect(composeValidationRules('wikimedia_commons', form, false)).toEqual({ category: 'Sacramento', target_count: 1 })
  })

  it('wikidata_statement: normalised qid and property list', () => {
    const form = { ...defaultRuleForm(), qid: ' q111393295', properties: 'p84, P571' }
    expect(composeValidationRules('wikidata_statement', form, false)).toEqual({
      qid: 'Q111393295',
      properties: ['P84', 'P571'],
      target_count: 1
    })
  })

  it('ohm_feature defaults to any start_date', () => {
    expect(composeValidationRules('ohm_feature', defaultRuleForm(), false)).toEqual({
      required_tags: { start_date: '*' },
      target_count: 1
    })
  })

  it('oss_contribution: kinds and optional owners', () => {
    const form = { ...defaultRuleForm(), kinds: { pr: true, issue: false } }
    expect(composeValidationRules('oss_contribution', form, false)).toEqual({ kinds: ['pr'], target_count: 1 })
    form.allowedOwners = 'OSGeo, qgis'
    expect(composeValidationRules('oss_contribution', form, false)).toEqual({
      kinds: ['pr'],
      allowed_owners: ['OSGeo', 'qgis'],
      target_count: 1
    })
  })

  it('location_checkin: radius and minutes, no target_count', () => {
    expect(composeValidationRules('location_checkin', defaultRuleForm(), true)).toEqual({ radius_m: 50, min_minutes: 0 })
  })

  it('count-only types and bad numbers fall back to a target_count of 1', () => {
    const form = { ...defaultRuleForm(), targetCount: NaN }
    for (const type of ['wikidata_entry', 'osm_notes', 'street_imagery'] as const) {
      expect(composeValidationRules(type, form, false)).toEqual({ target_count: 1 })
    }
  })
})

describe('validateRuleForm', () => {
  it('requires the inputs each type cannot work without', () => {
    const form = defaultRuleForm()
    expect(validateRuleForm('osm_tags', form, false)).toBeNull()
    expect(validateRuleForm('wikidata_statement', form, false)).toMatch(/item id/)
    expect(validateRuleForm('wikidata_statement', { ...form, qid: 'Q1', properties: 'P84, nope' }, false)).toMatch(/property/)
    expect(validateRuleForm('wikidata_statement', { ...form, qid: 'Q1', properties: 'P84' }, false)).toBeNull()
    expect(validateRuleForm('oss_contribution', { ...form, kinds: { pr: false, issue: false } }, false)).toMatch(/pull requests/)
    expect(validateRuleForm('location_checkin', form, false)).toMatch(/target point/)
    expect(validateRuleForm('location_checkin', form, true)).toBeNull()
    expect(validateRuleForm('osm_tags', { ...form, osmTags: [{ key: ' ', value: 'x' }] }, false)).toMatch(/tag/)
  })
})

describe('helpers', () => {
  it('tagsToObject treats blank values as "*" and drops blank keys', () => {
    expect(tagsToObject([{ key: 'natural', value: 'tree' }, { key: 'leaf_type', value: '' }, { key: '', value: 'x' }])).toEqual({
      natural: 'tree',
      leaf_type: '*'
    })
  })

  it('splitList accepts commas and whitespace', () => {
    expect(splitList(' P84,P571  P31 ,')).toEqual(['P84', 'P571', 'P31'])
  })
})

describe('rulesToForm (inverse of composeValidationRules)', () => {
  // [type, canonical validation_rules, point target?] for every type, shaped like the seeded quests
  const cases: [CriteriaType, Record<string, any>, boolean][] = [
    ['osm_tags', { required_tags: { amenity: 'restaurant|cafe', opening_hours: '*' }, target_count: 5, require_hashtag: true }, false],
    ['osm_tags', { required_tags: { architect: '*', wikidata: '*' }, target_count: 1, require_hashtag: false, radius_m: 120 }, true],
    ['osm_tags', { required_tags: { emergency: 'fire_hydrant|defibrillator' }, target_count: 3, require_hashtag: true, action: 'create' }, false],
    ['osm_tags', { required_tags: { highway: 'crossing', kerb: '*' }, target_count: 5, require_hashtag: true, action: 'modify' }, false],
    ['wikimedia_commons', { category: 'Capitol Park (Sacramento)', target_count: 4 }, false],
    ['wikimedia_commons', { target_count: 1 }, true],
    ['wikidata_entry', { target_count: 2 }, true],
    ['wikidata_statement', { qid: 'Q111393295', properties: ['P84', 'P571'], target_count: 1 }, true],
    ['osm_notes', { target_count: 3 }, false],
    ['ohm_feature', { required_tags: { start_date: '*', building: 'yes' }, target_count: 1 }, false],
    ['oss_contribution', { kinds: ['pr', 'issue'], allowed_owners: ['OSGeo', 'qgis'], target_count: 1 }, false],
    ['oss_contribution', { kinds: ['issue'], target_count: 2 }, false],
    ['location_checkin', { radius_m: 60, min_minutes: 5 }, true],
    ['street_imagery', { target_count: 1 }, false]
  ]

  it('covers every type', () => {
    expect(new Set(cases.map(([type]) => type))).toEqual(new Set(CRITERIA_TYPES))
  })

  it.each(cases)('%s round-trips %j', (type, rules, hasPoint) => {
    const form = rulesToForm(type, rules)
    expect(validateRuleForm(type, form, hasPoint)).toBeNull()
    expect(composeValidationRules(type, form, hasPoint)).toEqual(rules)
  })

  it('round-trips the default form for every type', () => {
    for (const type of CRITERIA_TYPES) {
      const rules = composeValidationRules(type, defaultRuleForm(), true)
      expect(composeValidationRules(type, rulesToForm(type, rules), true)).toEqual(rules)
    }
  })

  it('fills missing keys from the defaults', () => {
    const form = rulesToForm('osm_tags', {})
    expect(form.osmTags).toEqual([])
    expect(form.targetCount).toBe(1)
    expect(form.requireHashtag).toBe(true)
    expect(form.osmRadiusM).toBe(300)
    expect(form.osmAction).toBe('any')
    expect(rulesToForm('osm_tags', { action: 'delete' }).osmAction).toBe('any')
    expect(rulesToForm('oss_contribution', null).kinds).toEqual({ pr: true, issue: true })
    expect(rulesToForm('location_checkin', { radius_m: 'x' }).checkinRadiusM).toBe(50)
  })

  it('objectToTags turns values into strings', () => {
    expect(objectToTags({ capacity: 4, image: null })).toEqual([
      { key: 'capacity', value: '4' },
      { key: 'image', value: '*' }
    ])
    expect(objectToTags(undefined)).toEqual([])
  })

  it('unmodelledRules returns only the keys the form does not edit', () => {
    expect(unmodelledRules('osm_notes', { target_count: 1, status: 'closed' })).toEqual({ status: 'closed' })
    expect(unmodelledRules('location_checkin', { radius_m: 5, min_minutes: 0 })).toEqual({})
    // action is modelled for osm_tags, so changing it in the form is not undone on save
    expect(unmodelledRules('osm_tags', { action: 'create', note: 'x' })).toEqual({ note: 'x' })
  })
})

describe('value scoring (validation_rules.scoring)', () => {
  // The seeded "Stamped in Sacramento" quest
  const stampRules = {
    category: 'Sidewalk contractor stamps in Sacramento, California',
    target_count: 1,
    scoring: {
      value: { source: 'description', pattern: '\\b((?:18|19|20)\\d{2})\\b', kind: 'year' },
      per_bucket: { size: 10, points: 5 },
      extreme_bonus: { direction: 'min', points: 25 }
    }
  }

  it('is off by default and adds nothing to any type', () => {
    for (const type of CRITERIA_TYPES) {
      expect(composeValidationRules(type, defaultRuleForm(), true)).not.toHaveProperty('scoring')
    }
    expect(composeScoring(defaultScoringForm())).toBeNull()
  })

  it('switched on, the defaults are the sidewalk stamp rule with the default year pattern', () => {
    const form = { ...defaultRuleForm(), scoring: { ...defaultScoringForm(), enabled: true } }
    expect(composeValidationRules('wikimedia_commons', form, false)).toEqual({
      target_count: 1,
      scoring: {
        value: { source: 'description', pattern: DEFAULT_SCORING_PATTERNS.year, kind: 'year' },
        per_bucket: { size: 10, points: 5 },
        extreme_bonus: { direction: 'min', points: 25 }
      }
    })
  })

  it.each([
    ['wikimedia_commons', stampRules],
    // OHM start_date on every element, no pattern (backend default), max with no buckets
    ['ohm_feature', { required_tags: { start_date: '*' }, target_count: 1,
      scoring: { value: { source: 'tag:start_date', kind: 'year' }, extreme_bonus: { direction: 'max', points: 10 } } }],
    // Values entered by hosts only, numbers in buckets of 50
    ['osm_notes', { target_count: 2, scoring: { per_bucket: { size: 50, points: 2 } } }],
    ['osm_tags', { required_tags: { amenity: 'bench' }, target_count: 1, require_hashtag: true,
      scoring: { value: { source: 'tag:capacity', pattern: '\\d+', kind: 'number' }, per_bucket: { size: 5, points: 1 } } }]
  ] as [CriteriaType, Record<string, any>][])('%s round-trips %j', (type, rules) => {
    const form = rulesToForm(type, rules)
    expect(form.scoring.enabled).toBe(true)
    expect(validateRuleForm(type, form, false)).toBeNull()
    expect(composeValidationRules(type, form, false)).toEqual(rules)
  })

  it('scoringToForm reads the parts', () => {
    const form = scoringToForm({ value: { source: 'tag:start_date', kind: 'number' }, extreme_bonus: { direction: 'max', points: 3 } })
    expect(form).toMatchObject({ enabled: true, source: 'tag', tagKey: 'start_date', kind: 'number', pattern: '',
      bucketEnabled: false, bonusEnabled: true, bonusDirection: 'max', bonusPoints: 3 })
    expect(scoringToForm(undefined).enabled).toBe(false)
    expect(scoringToForm({ per_bucket: { size: 10, points: 5 } }).source).toBe('none')
  })

  it('validates the scoring inputs only when switched on', () => {
    const on = { ...defaultScoringForm(), enabled: true }
    const form = (scoring: Partial<typeof on>) => ({ ...defaultRuleForm(), scoring: { ...on, ...scoring } })
    expect(validateRuleForm('wikimedia_commons', form({}), false)).toBeNull()
    expect(validateRuleForm('ohm_feature', form({ source: 'tag', tagKey: ' ' }), false)).toMatch(/tag/)
    expect(validateRuleForm('wikimedia_commons', form({ bucketEnabled: false, bonusEnabled: false }), false)).toMatch(/both/)
    expect(validateRuleForm('wikimedia_commons', form({ bucketSize: 0 }), false)).toMatch(/bucket size/)
    expect(validateRuleForm('wikimedia_commons', form({ enabled: false, bucketSize: 0 }), false)).toBeNull()
  })

  it('patternForKind follows the kind unless the host wrote a pattern', () => {
    expect(patternForKind(DEFAULT_SCORING_PATTERNS.year, 'year', 'number')).toBe(DEFAULT_SCORING_PATTERNS.number)
    expect(patternForKind('', 'number', 'year')).toBe(DEFAULT_SCORING_PATTERNS.year)
    expect(patternForKind('stamp (\\d{4})', 'year', 'number')).toBe('stamp (\\d{4})')
  })

  it('scoring is modelled for every type, so switching it off on edit removes it', () => {
    for (const type of CRITERIA_TYPES) {
      expect(unmodelledRules(type, { scoring: { per_bucket: { size: 10, points: 5 } } })).toEqual({})
    }
  })
})
