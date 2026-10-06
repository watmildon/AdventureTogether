/**
 * Helpers for the back-office event pages: datetime-local <-> ISO conversion, hashtag
 * clean-up, event status badges and date ranges. Kept free of Vue so they can be unit-tested.
 */

import type { EventData } from '../api'

const pad = (n: number) => String(Math.abs(Math.trunc(n))).padStart(2, '0')

/**
 * "2026-11-02T08:00" (a datetime-local value, the host's own wall-clock time) to a full ISO
 * string carrying the host's UTC offset for that date, e.g. "2026-11-02T08:00:00-08:00".
 * Using the offset of that specific date keeps daylight-saving changes right.
 * Returns null for blank or unparseable input.
 */
export function localInputToIso(value: string | null | undefined): string | null {
  const match = value?.trim().match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/)
  if (!match) return null
  const [, y, m, d, hh, mm, ss] = match
  const date = new Date(Number(y), Number(m) - 1, Number(d), Number(hh), Number(mm), Number(ss || 0))
  if (Number.isNaN(date.getTime())) return null
  // getTimezoneOffset is minutes *behind* UTC (480 for UTC-8), hence the inverted sign
  const offset = -date.getTimezoneOffset()
  const sign = offset >= 0 ? '+' : '-'
  const local = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  return `${local}${sign}${pad(offset / 60)}:${pad(offset % 60)}`
}

/** An ISO timestamp (any offset) as a datetime-local value in the host's time zone; '' when invalid. */
export function isoToLocalInput(iso: string | null | undefined): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** "#FOSS4GNA2026 " -> "FOSS4GNA2026": hosts often paste the hashtag with its '#'. */
export function normaliseHashtag(value: string): string {
  return value.trim().replace(/^#+/, '').trim()
}

/** Hosts the API accepts for schedule_url (its SCHEDULE_URL_ALLOWED_HOSTS default). */
export const SCHEDULE_URL_HOSTS = ['talks.osgeo.org', 'pretalx.com']

export type EventStatus = 'inactive' | 'upcoming' | 'live' | 'ended'

/** Inactive wins; otherwise where `now` falls relative to the event's start and end. */
export function eventStatus(event: Pick<EventData, 'is_active' | 'start_time' | 'end_time'>, now: Date = new Date()): EventStatus {
  if (!event.is_active) return 'inactive'
  const t = now.getTime()
  if (t < new Date(event.start_time).getTime()) return 'upcoming'
  if (t > new Date(event.end_time).getTime()) return 'ended'
  return 'live'
}

export const EVENT_STATUS_LABELS: Record<EventStatus, { label: string; badge: string }> = {
  live: { label: 'Live', badge: 'badge-success' },
  upcoming: { label: 'Upcoming', badge: 'badge-primary' },
  ended: { label: 'Ended', badge: 'badge-warning' },
  inactive: { label: 'Inactive', badge: 'badge-danger' }
}

/** "Mon 2 Nov 2026, 08:00 – Wed 4 Nov 2026, 18:00" in the viewer's time zone. */
export function formatEventRange(start: string, end: string): string {
  const fmt = (iso: string) => {
    const date = new Date(iso)
    return Number.isNaN(date.getTime())
      ? ''
      : date.toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  }
  return [fmt(start), fmt(end)].filter(Boolean).join(' – ')
}

export const HARVEST_STAT_KEYS = ['harvested', 'created', 'updated', 'matched', 'errors'] as const

export interface HarvestRow {
  platform: string
  counts: Record<(typeof HARVEST_STAT_KEYS)[number], number>
}

/**
 * The per-platform entries of a trigger_harvest `stats` object, in the order the server ran
 * them. Everything that is not a platform (summary, warnings, event, found, dry_run,
 * would_submit) is skipped; missing counters read as 0.
 */
export function harvestPlatformRows(stats: Record<string, any> | null | undefined): HarvestRow[] {
  if (!stats) return []
  const skip = new Set(['summary', 'warnings', 'event', 'found', 'dry_run', 'would_submit'])
  return Object.entries(stats)
    .filter(([key, value]) => !skip.has(key) && value && typeof value === 'object' && !Array.isArray(value))
    .map(([platform, value]) => ({
      platform,
      counts: Object.fromEntries(HARVEST_STAT_KEYS.map((k) => [k, Number(value[k]) || 0])) as HarvestRow['counts']
    }))
}
