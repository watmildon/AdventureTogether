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
  },
  mangrove_review: {
    label: 'Mangrove place review',
    shortLabel: 'Review',
    icon: '💬',
    description: 'Review a place in the area on Mangrove (open reviews, no account). Use your display name as the nickname and put the event hashtag in the review.',
    helpApp: 'mangrove.reviews',
    colorToken: '--color-type-review',
    color: '#0f766e'
  },
  maproulette_task: {
    label: 'MapRoulette task',
    shortLabel: 'MapRoulette',
    icon: '🎯',
    description: 'Fix MapRoulette tasks in the area, logged in with your OpenStreetMap account so your OSM username can be credited.',
    helpApp: 'maproulette.org',
    colorToken: '--color-type-maproulette',
    color: '#4338ca'
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
  panoramax: { label: 'Panoramax', type: 'street_imagery' },
  mangrove: { label: 'Mangrove Reviews', type: 'mangrove_review' },
  maproulette: { label: 'MapRoulette', type: 'maproulette_task' }
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

/**
 * Tools a participant can say they have (landing page "Tools I have" checklist). The quest
 * panel uses them to hide quests the participant has no way to do. Links point at official
 * project pages, which carry the current store/download links.
 */
export type ToolId =
  | 'streetcomplete'
  | 'everydoor'
  | 'osm_web'
  | 'commons'
  | 'wikidata'
  | 'ohm_editor'
  | 'github'
  | 'panoramax'
  | 'mangrove'
  | 'maproulette'

export interface ToolInfo {
  id: ToolId
  label: string
  /** One line on what it is and where it runs. */
  description: string
  links: { label: string; url: string }[]
}

export const TOOLS: ToolInfo[] = [
  {
    id: 'streetcomplete',
    label: 'StreetComplete',
    description: 'Phone app that asks simple questions about what is around you and saves the answers to OpenStreetMap.',
    links: [{ label: 'Get the app', url: 'https://streetcomplete.app/' }]
  },
  {
    id: 'everydoor',
    label: 'EveryDoor',
    description: 'Phone app (Android and iOS) for adding shops, entrances and other points to OpenStreetMap on the go.',
    links: [{ label: 'Get the app', url: 'https://every-door.app/' }]
  },
  {
    id: 'osm_web',
    label: 'OpenStreetMap web editor (iD)',
    description: 'Edit OpenStreetMap in any browser, and comment on or resolve map notes. Needs a free OSM account.',
    links: [{ label: 'Open the editor', url: 'https://www.openstreetmap.org/edit' }]
  },
  {
    id: 'commons',
    label: 'Wikimedia Commons',
    description: 'Upload photos with the Commons Android app or the web Upload Wizard. Needs a Wikimedia account.',
    links: [
      { label: 'Android app', url: 'https://play.google.com/store/apps/details?id=fr.free.nrw.commons' },
      { label: 'Web upload', url: 'https://commons.wikimedia.org/wiki/Special:UploadWizard' }
    ]
  },
  {
    id: 'wikidata',
    label: 'Wikidata',
    description: 'Add facts and statements to Wikidata items in the browser, with the same Wikimedia account.',
    links: [{ label: 'Open Wikidata', url: 'https://www.wikidata.org/' }]
  },
  {
    id: 'ohm_editor',
    label: 'OpenHistoricalMap editor',
    description: 'Map how places used to be, in the browser. Sign in with your OpenStreetMap account.',
    links: [{ label: 'Open the editor', url: 'https://www.openhistoricalmap.org/edit' }]
  },
  {
    id: 'github',
    label: 'GitHub account',
    description: 'Open pull requests or issues on open source projects for code contribution quests.',
    links: [{ label: 'Sign up', url: 'https://github.com/signup' }]
  },
  {
    id: 'panoramax',
    label: 'Panoramax',
    description: 'Capture and upload street-level photo sequences to the open Panoramax imagery commons.',
    links: [{ label: 'About and apps', url: 'https://wiki.openstreetmap.org/wiki/Panoramax' }]
  },
  {
    id: 'mangrove',
    label: 'Mangrove Reviews (web, mangrove.reviews)',
    description: 'Write open reviews of places in the browser. No account needed; set your nickname to your display name here.',
    links: [{ label: 'Open Mangrove', url: 'https://mangrove.reviews/' }]
  },
  {
    id: 'maproulette',
    label: 'MapRoulette (web, maproulette.org, OSM login)',
    description: 'Fix small OpenStreetMap tasks one at a time in the browser. Sign in with your OpenStreetMap account.',
    links: [{ label: 'Open MapRoulette', url: 'https://maproulette.org/' }]
  }
]

/** Tools by id, for labels in "Needs: ..." lines. */
export const TOOLS_BY_ID = Object.fromEntries(TOOLS.map((tool) => [tool.id, tool])) as Record<ToolId, ToolInfo>

/**
 * Which tools make each quest type doable: having any one of them is enough. An empty list
 * means the quest needs no tool at all (check-ins only need this map open).
 */
export const questTypeTools: Record<CriteriaType, ToolId[]> = {
  osm_tags: ['streetcomplete', 'everydoor', 'osm_web'],
  osm_notes: ['osm_web', 'streetcomplete'],
  ohm_feature: ['ohm_editor'],
  wikimedia_commons: ['commons'],
  wikidata_entry: ['wikidata'],
  wikidata_statement: ['wikidata'],
  oss_contribution: ['github'],
  street_imagery: ['panoramax'],
  mangrove_review: ['mangrove'],
  maproulette_task: ['maproulette'],
  location_checkin: []
}

/**
 * True when the participant has at least one tool that can complete a quest of this type.
 * Check-ins are always doable; unknown (newer) types are treated as doable rather than hidden.
 */
export function canDoQuest(criteriaType: string, tools: readonly string[]): boolean {
  const needed = questTypeTools[criteriaType as CriteriaType]
  if (!needed || needed.length === 0) return true
  return needed.some((tool) => tools.includes(tool))
}

/** "StreetComplete, EveryDoor or OpenStreetMap web editor (iD)"; '' when the type needs nothing. */
export function toolsNeededText(criteriaType: string): string {
  const labels = (questTypeTools[criteriaType as CriteriaType] || []).map((id) => TOOLS_BY_ID[id].label)
  if (labels.length <= 1) return labels[0] || ''
  return `${labels.slice(0, -1).join(', ')} or ${labels[labels.length - 1]}`
}

/** Composable wrapper so components can destructure the helpers in the usual Vue style. */
export function useQuestTypes() {
  return { QUEST_TYPES, CRITERIA_TYPES, questTypeFor, platformInfo, formatSessionLine, formatQuestWindow, TOOLS, canDoQuest, toolsNeededText }
}
