import { describe, it, expect } from 'vitest'
import { checkinStateFor, mergePingCheckins, mergeRecordedCheckins, questMinMinutes } from '../checkinState'
import type { CheckinData, PingCheckin } from '../../api'

const row = (quest: number, status: CheckinData['status'], extra: Partial<CheckinData> = {}): CheckinData => ({
  quest, quest_title: `Quest ${quest}`, status, ...extra
})
const ping = (quest: number, status: PingCheckin['status']): PingCheckin => ({ quest, quest_title: `Quest ${quest}`, status })

describe('checkinStateFor', () => {
  it('counts only verified as checked in', () => {
    expect(checkinStateFor('verified')).toBe('verified')
    expect(checkinStateFor('verified', 5)).toBe('verified')
  })

  it('maps pending and in_range to in range, or dwelling when the quest needs a dwell time', () => {
    expect(checkinStateFor('pending')).toBe('in_range')
    expect(checkinStateFor('pending', 0)).toBe('in_range')
    expect(checkinStateFor('pending', 5)).toBe('dwelling')
    expect(checkinStateFor('in_range', null)).toBe('in_range')
    expect(checkinStateFor('in_range', 3)).toBe('dwelling')
  })

  it('shows nothing for revoked or unknown statuses', () => {
    expect(checkinStateFor('revoked')).toBeNull()
    expect(checkinStateFor('revoked', 5)).toBeNull()
    expect(checkinStateFor(undefined)).toBeNull()
    expect(checkinStateFor('something-new')).toBeNull()
  })
})

describe('questMinMinutes', () => {
  it('reads validation_rules.min_minutes, defaulting to 0 on missing or bad input', () => {
    expect(questMinMinutes({ validation_rules: { min_minutes: 5 } })).toBe(5)
    expect(questMinMinutes({ validation_rules: { min_minutes: '2' } })).toBe(2)
    expect(questMinMinutes({ validation_rules: {} })).toBe(0)
    expect(questMinMinutes({ validation_rules: { min_minutes: 'abc' } })).toBe(0)
    expect(questMinMinutes({ validation_rules: { min_minutes: -1 } })).toBe(0)
    expect(questMinMinutes(undefined)).toBe(0)
  })
})

describe('mergeRecordedCheckins (reload)', () => {
  it('maps verified, pending and revoked records; revoked never shows as done', () => {
    const next = mergeRecordedCheckins({}, [
      row(1, 'verified'),
      row(2, 'pending', { min_minutes: 5 }),
      row(3, 'pending', { min_minutes: 0 }),
      row(4, 'revoked')
    ])
    expect(next).toEqual({ 1: 'verified', 2: 'dwelling', 3: 'in_range' })
  })

  it("falls back to the quest's dwell time when the record has none", () => {
    expect(mergeRecordedCheckins({}, [row(2, 'pending')], (id) => (id === 2 ? 10 : 0))).toEqual({ 2: 'dwelling' })
  })

  it('keeps fresher ping state over pending records but lets verified records win', () => {
    const next = mergeRecordedCheckins({ 1: 'in_range', 2: 'in_range' }, [row(1, 'verified'), row(2, 'pending', { min_minutes: 5 })])
    expect(next).toEqual({ 1: 'verified', 2: 'in_range' })
  })

  it('ignores rows without a quest id', () => {
    expect(mergeRecordedCheckins({}, [{ ...row(1, 'verified'), quest: null }])).toEqual({})
  })
})

describe('mergePingCheckins', () => {
  it('maps ping statuses, keeps verified sticky and replaces in-range state', () => {
    const { next, newlyVerified, firstSeen } = mergePingCheckins(
      { 1: 'verified', 2: 'in_range', 3: 'dwelling' },
      [ping(3, 'verified'), ping(4, 'in_range'), ping(5, 'in_range')],
      (id) => (id === 5 ? 5 : 0)
    )
    // 2 left range and is dropped; 3 became verified; 4 and 5 are new
    expect(next).toEqual({ 1: 'verified', 3: 'verified', 4: 'in_range', 5: 'dwelling' })
    expect(newlyVerified).toBe(true)
    expect(firstSeen.map((c) => c.quest)).toEqual([4, 5])
  })

  it('does not re-report or downgrade an already verified quest', () => {
    const { next, newlyVerified, firstSeen } = mergePingCheckins({ 1: 'verified' }, [ping(1, 'in_range')])
    expect(next).toEqual({ 1: 'verified' })
    expect(newlyVerified).toBe(false)
    expect(firstSeen).toEqual([])
  })

  it('skips malformed items and unknown statuses', () => {
    const { next } = mergePingCheckins({}, [null as any, { quest: 'x' } as any, { quest: 6, status: 'revoked' } as any])
    expect(next).toEqual({})
  })
})
