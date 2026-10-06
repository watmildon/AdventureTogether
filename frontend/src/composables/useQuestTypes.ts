/**
 * Shared presentation metadata for quest criteria types and submission platforms,
 * plus formatters for the session ("inspired by") line and quest time windows.
 *
 * Views use this so a quest type looks the same everywhere: the participant's quest
 * panel, map popups, the host builder and the verification table.
 */

import type { CriteriaType, InspiredBy, SubmissionPlatform } from '../api'

export interface QuestTypeInfo {
  /** Full name shown in pickers and quest cards. */
  label: string
  /** Compact name for badges. */
  shortLabel: string
  /** Emoji used as the type icon (no icon font in this app). */
  icon: string
  /** One-line explanation of what the participant has to do. */
  description: string
  /** The app or site participants should use to complete it. */
  helpApp: string
  /** CSS custom property (see tokens.css) for the type's accent colour. */
  colorToken: string
  /** Same colour as a literal, for Leaflet path styles. */
  color: string
  /** True when the server cannot verify this type yet. */
  comingSoon?: boolean
}

export const QUEST_TYPES: Record<CriteriaType, QuestTypeInfo> = {
  osm_tags: {
    label: 'OpenStreetMap tags',
    shortLabel: 'OSM',
    icon: '🗺️',
    description: 'Edit OpenStreetMap features in the area so they carry the required tags. Put the event hashtag in the changeset comment.',
    helpApp: 'StreetComplete / EveryDoor',
    colorToken: '--color-type-osm',
    color: '#16a34a'
  },
  wikimedia_commons: {
    label: 'Wikimedia Commons photo',
    shortLabel: 'Commons',
    icon: '📸',
    description: 'Upload a photo to Wikimedia Commons with the event hashtag in its description.',
    helpApp: 'Commons app',
    colorToken: '--color-type-commons',
    color: '#0369a1'
  },
  wikidata_entry: {
    label: 'Wikidata edit',
    shortLabel: 'Wikidata',
    icon: '📊',
    description: 'Make Wikidata edits with the event hashtag in the edit summary.',
    helpApp: 'Wikidata',
    colorToken: '--color-type-wikidata',
    color: '#9f1239'
  },
  wikidata_statement: {
    label: 'Wikidata statement',
    shortLabel: 'Statement',
    icon: '🧾',
    description: 'Add specific properties to a named Wikidata item, with the event hashtag in the edit summary.',
    helpApp: 'Wikidata',
    colorToken: '--color-type-wikidata-statement',
    color: '#be123c'
  },
  location_checkin: {
    label: 'Location check-in',
    shortLabel: 'Check-in',
    icon: '📍',
    description: 'Go to the target and keep this map open while you are there. Verified automatically from your location pings.',
    helpApp: 'This map (keep it open)',
    colorToken: '--color-type-checkin',
    color: '#d97706'
  },
  osm_notes: {
    label: 'OpenStreetMap Note',
    shortLabel: 'Notes',
    icon: '📝',
    description: 'Resolve an open OSM Note in the event area, or open a new one, with the event hashtag in the comment.',
    helpApp: 'openstreetmap.org / StreetComplete',
    colorToken: '--color-type-notes',
    color: '#0891b2'
  },
  ohm_feature: {
    label: 'OpenHistoricalMap feature',
    shortLabel: 'OHM',
    icon: '🕰️',
    description: 'Add a historical feature with a start_date to OpenHistoricalMap in the event area, hashtag in the changeset comment.',
    helpApp: 'OHM iD editor',
    colorToken: '--color-type-ohm',
    color: '#7c3aed'
  },
  oss_contribution: {
    label: 'Open source contribution',
    shortLabel: 'Code',
    icon: '💻',
    description: 'Open a pull request or issue on an open source project with the event hashtag in the body.',
    helpApp: 'GitHub',
    colorToken: '--color-type-code',
    color: '#334155'
  },
  street_imagery: {
    label: 'Street-level imagery',
    shortLabel: 'Imagery',
    icon: '🛣️',
    description: 'Upload street-level photo sequences in the event area. Coming soon: not verified automatically yet.',
    helpApp: 'Panoramax',
    colorToken: '--color-type-imagery',
    color: '#db2777',
    comingSoon: true
  }
}

/** Every criteria type in display order (builder picker, filters). */
export const CRITERIA_TYPES = Object.keys(QUEST_TYPES) as CriteriaType[]

/** Fallback for a criteria type this frontend does not know (e.g. a newer server). */
const UNKNOWN_TYPE: QuestTypeInfo = {
  label: 'Quest',
  shortLabel: 'Quest',
  icon: '⭐',
  description: '',
  helpApp: '',
  colorToken: '--color-primary',
  color: '#2563eb'
}

export function questTypeFor(type: string | null | undefined): QuestTypeInfo {
  return (type && QUEST_TYPES[type as CriteriaType]) || { ...UNKNOWN_TYPE, label: type || UNKNOWN_TYPE.label }
}

/** Submission platforms, with the quest type whose icon/colour they share. */
export const PLATFORMS: Record<SubmissionPlatform, { label: string; type: CriteriaType }> = {
  osm: { label: 'OpenStreetMap', type: 'osm_tags' },
  commons: { label: 'Wikimedia Commons', type: 'wikimedia_commons' },
  wikidata: { label: 'Wikidata', type: 'wikidata_entry' },
  ohm: { label: 'OpenHistoricalMap', type: 'ohm_feature' },
  osm_notes: { label: 'OSM Notes', type: 'osm_notes' },
  checkin: { label: 'Check-in', type: 'location_checkin' },
  github: { label: 'GitHub', type: 'oss_contribution' },
  panoramax: { label: 'Panoramax', type: 'street_imagery' }
}

/** Badge data for a submission platform; unknown platforms get the generic icon and their raw key. */
export function platformInfo(platform: string, display?: string | null): { label: string; icon: string; color: string } {
  const known = PLATFORMS[platform as SubmissionPlatform]
  const type = questTypeFor(known?.type)
  return { label: display || known?.label || platform, icon: type.icon, color: type.color }
}

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const pad = (n: number) => String(n).padStart(2, '0')

/**
 * "Wed 11:00" from a session's ISO start time, using the wall-clock time written in
 * the string (the conference's local time) rather than the viewer's time zone, so a
 * remote host sees the same time that is printed in the programme.
 */
export function formatSessionTime(iso: string | null | undefined): string {
  const match = iso?.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
  if (!match) return ''
  const [, y, m, d, hh, mm] = match
  const weekday = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d))).getUTCDay()
  return `${DAY_NAMES[weekday]} ${hh}:${mm}`
}

export interface SessionLine {
  /** Session title (falls back to the URL for hand-entered sessions without a title). */
  title: string
  /** "Speaker A, Speaker B · Wed 11:00 · Room", or '' when nothing is known. */
  details: string
  /** The whole line as plain text, e.g. for popups and aria labels. */
  text: string
  url: string | null
}

/**
 * Formats a quest's `inspired_by` as
 * "Inspired by: OpenHistoricalMap: across the geoverse — Minh Nguyễn · Wed 11:00 · Beavis".
 * Returns null for `{}`/null so callers can simply skip the line.
 */
export function formatSessionLine(inspired: InspiredBy | null | undefined): SessionLine | null {
  if (!inspired) return null
  const title = (inspired.title || inspired.url || '').trim()
  if (!title) return null

  const speakers = (inspired.speakers || []).filter(Boolean).join(', ')
  const details = [speakers, formatSessionTime(inspired.start), inspired.room || '']
    .filter(Boolean)
    .join(' · ')

  return {
    title,
    details,
    text: `Inspired by: ${title}${details ? ` — ${details}` : ''}`,
    url: inspired.url || null
  }
}

/**
 * "Mon 18:00–20:00" for a quest window in the viewer's local time (participants are
 * at the event). Spanning days gives "Mon 18:00 – Tue 02:00"; open-ended windows give
 * "From …" / "Until …". Returns null when the quest has no window.
 */
export function formatQuestWindow(start?: string | null, end?: string | null): string | null {
  const parse = (iso?: string | null) => {
    if (!iso) return null
    const date = new Date(iso)
    return Number.isNaN(date.getTime()) ? null : date
  }
  const s = parse(start)
  const e = parse(end)
  const day = (d: Date) => DAY_NAMES[d.getDay()]
  const time = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`

  if (s && e) {
    return s.toDateString() === e.toDateString()
      ? `${day(s)} ${time(s)}–${time(e)}`
      : `${day(s)} ${time(s)} – ${day(e)} ${time(e)}`
  }
  if (s) return `From ${day(s)} ${time(s)}`
  if (e) return `Until ${day(e)} ${time(e)}`
  return null
}

/** Composable wrapper so components can destructure the helpers in the usual Vue style. */
export function useQuestTypes() {
  return { QUEST_TYPES, CRITERIA_TYPES, questTypeFor, platformInfo, formatSessionLine, formatQuestWindow }
}
