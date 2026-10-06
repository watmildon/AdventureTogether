import { describe, it, expect } from 'vitest'
import {
  questScoring,
  formatValue,
  formatBucket,
  bucketNoun,
  bucketsLine,
  extremeWord,
  scoringSummary
} from '../valueScoring'

const stampQuest = {
  validation_rules: {
    scoring: {
      value: { source: 'description', kind: 'year' },
      per_bucket: { size: 10, points: 5 },
      extreme_bonus: { direction: 'min', points: 25 }
    }
  }
}

describe('valueScoring helpers', () => {
  it('questScoring normalises the rule, null without one', () => {
    expect(questScoring(stampQuest)).toEqual({ kind: 'year', bucketSize: 10, bucketPoints: 5, direction: 'min', bonusPoints: 25 })
    expect(questScoring({ validation_rules: { scoring: { value: { kind: 'number' }, extreme_bonus: { direction: 'max', points: 3 } } } }))
      .toEqual({ kind: 'number', bucketSize: null, bucketPoints: 0, direction: 'max', bonusPoints: 3 })
    expect(questScoring({ validation_rules: { target_count: 1 } })).toBeNull()
    expect(questScoring(null)).toBeNull()
  })

  it('formats buckets by kind: decades for years, ranges otherwise', () => {
    expect(formatBucket(1920, 10, 'year')).toBe('1920s')
    expect(formatBucket(1900, 25, 'year')).toBe('1900–1924')
    expect(formatBucket(0, 10, 'number')).toBe('0–9')
    expect(formatBucket(1000, 500, 'number')).toBe('1,000–1,499')
    expect(formatBucket(0.5, 0.5, 'number')).toBe('0.5–1')
    expect(bucketNoun(10, 'year')).toBe('Decades')
    expect(bucketNoun(100, 'year')).toBe('Centuries')
    expect(bucketNoun(10, 'number')).toBe('Ranges')
  })

  it('bucketsLine lists the buckets in order', () => {
    const scoring = questScoring(stampQuest)!
    expect(bucketsLine([1950, 1920], scoring)).toBe('Decades found: 1920s, 1950s')
    expect(bucketsLine([], scoring)).toBeNull()
    expect(bucketsLine([0, 10], { ...scoring, kind: 'number' })).toBe('Ranges found: 0–9, 10–19')
  })

  it('formats values and names the extreme', () => {
    expect(formatValue(1923, 'year')).toBe('1923')
    expect(formatValue(1250.5, 'number')).toBe('1,250.5')
    expect(formatValue(null, 'year')).toBe('')
    expect(extremeWord('min', 'year')).toBe('oldest')
    expect(extremeWord('max', 'year')).toBe('newest')
    expect(extremeWord('max', 'number')).toBe('highest')
  })

  it('scoringSummary states the rule', () => {
    expect(scoringSummary(questScoring(stampQuest)!)).toBe('+5 per decade, +25 for the oldest')
    expect(scoringSummary({ kind: 'number', bucketSize: 50, bucketPoints: 2, direction: 'min', bonusPoints: null })).toBe('+2 per range of 50')
  })
})
