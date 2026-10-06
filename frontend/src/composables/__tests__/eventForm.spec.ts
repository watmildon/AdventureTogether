import { describe, it, expect } from 'vitest'
import {
  localInputToIso,
  isoToLocalInput,
  normaliseHashtag,
  eventStatus,
  harvestPlatformRows
} from '../eventForm'

// Assertions are written against the test machine's own time zone, so they hold in any TZ.
describe('datetime-local <-> ISO', () => {
  it('converts a local input to ISO with the offset for that date', () => {
    const iso = localInputToIso('2026-11-02T08:30')!
    expect(iso).toMatch(/^2026-11-02T08:30:00[+-]\d{2}:\d{2}$/)
    // Same instant as the local wall-clock time
    expect(new Date(iso).getTime()).toBe(new Date(2026, 10, 2, 8, 30).getTime())
  })

  it("uses each date's own offset (daylight saving)", () => {
    for (const [input, local] of [
      ['2026-01-15T12:00', new Date(2026, 0, 15, 12, 0)],
      ['2026-07-15T12:00', new Date(2026, 6, 15, 12, 0)]
    ] as const) {
      const iso = localInputToIso(input)!
      expect(new Date(iso).getTime()).toBe(local.getTime())
      const minutes = -local.getTimezoneOffset()
      const sign = minutes >= 0 ? '+' : '-'
      const hh = String(Math.floor(Math.abs(minutes) / 60)).padStart(2, '0')
      const mm = String(Math.abs(minutes) % 60).padStart(2, '0')
      expect(iso.endsWith(`${sign}${hh}:${mm}`)).toBe(true)
    }
  })

  it('returns null for blank or malformed input', () => {
    expect(localInputToIso('')).toBeNull()
    expect(localInputToIso(null)).toBeNull()
    expect(localInputToIso('2026-11-02')).toBeNull()
    expect(localInputToIso('next tuesday')).toBeNull()
  })

  it('shows an ISO time from the API as the host’s local wall-clock time', () => {
    const iso = '2026-11-02T16:00:00Z'
    const local = isoToLocalInput(iso)
    expect(local).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
    expect(new Date(localInputToIso(local)!).getTime()).toBe(new Date(iso).getTime())
    expect(isoToLocalInput('')).toBe('')
    expect(isoToLocalInput('garbage')).toBe('')
  })

  it('round-trips local input -> ISO -> local input', () => {
    expect(isoToLocalInput(localInputToIso('2026-11-04T18:45'))).toBe('2026-11-04T18:45')
  })
})

describe('normaliseHashtag', () => {
  it('strips leading # and whitespace', () => {
    expect(normaliseHashtag('#FOSS4GNA2026')).toBe('FOSS4GNA2026')
    expect(normaliseHashtag('  ##BOTest ')).toBe('BOTest')
    expect(normaliseHashtag('Plain')).toBe('Plain')
  })
})

describe('eventStatus', () => {
  const event = { is_active: true, start_time: '2026-11-02T16:00:00Z', end_time: '2026-11-05T02:00:00Z' }
  it('is inactive, upcoming, live or ended', () => {
    expect(eventStatus({ ...event, is_active: false }, new Date('2026-11-03T00:00:00Z'))).toBe('inactive')
    expect(eventStatus(event, new Date('2026-10-06T00:00:00Z'))).toBe('upcoming')
    expect(eventStatus(event, new Date('2026-11-03T00:00:00Z'))).toBe('live')
    expect(eventStatus(event, new Date('2026-11-06T00:00:00Z'))).toBe('ended')
  })
})

describe('harvestPlatformRows', () => {
  it('keeps platform entries and skips summary and metadata', () => {
    const rows = harvestPlatformRows({
      event: 2,
      dry_run: false,
      found: true,
      summary: { harvested: 5, created: 2, updated: 0, matched: 2, errors: 1 },
      warnings: ['github: rate limited'],
      osm: { harvested: 4, created: 2, updated: 0, matched: 2, errors: 0 },
      github: { harvested: 1, errors: 1 }
    })
    expect(rows.map((r) => r.platform)).toEqual(['osm', 'github'])
    expect(rows[1].counts).toEqual({ harvested: 1, created: 0, updated: 0, matched: 0, errors: 1 })
    expect(harvestPlatformRows(null)).toEqual([])
  })
})
