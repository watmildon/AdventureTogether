import { describe, it, expect } from 'vitest'
import {
  composeValidationRules,
  defaultRuleForm,
  validateRuleForm,
  tagsToObject,
  splitList,
  rulesToForm,
  unmodelledRules,
  objectToTags
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
  })
})
