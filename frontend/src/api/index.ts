/**
 * AdventureTogether Frontend API Client
 */

export interface EventData {
  id: number
  title: string
  slug: string
  description: string
  hashtag: string
  bounding_polygon: any
  start_time: string
  end_time: string
  /** Optional pretalx/frab schedule export used by the sessions endpoint ('' when unset). */
  schedule_url?: string
  is_active: boolean
  created_at: string
}

/** Optional platform usernames a participant gives so harvested edits are credited to their team. */
export interface PlatformUsernames {
  osm_username?: string
  wikimedia_username?: string
  github_username?: string
}

export interface TeamMembershipData extends PlatformUsernames {
  id: number
  user_identifier: string
  display_name: string
  joined_at: string
}

export interface TeamData {
  id: number
  event: number
  name: string
  join_code: string
  score: number
  member_count: number
  memberships: TeamMembershipData[]
  created_at: string
}

/** Every quest verification type the backend understands. */
export type CriteriaType =
  | 'osm_tags'
  | 'wikimedia_commons'
  | 'wikidata_entry'
  | 'location_checkin'
  | 'osm_notes'
  | 'ohm_feature'
  | 'wikidata_statement'
  | 'oss_contribution'
  | 'street_imagery'

/**
 * The conference session a quest is tied to. Every field is optional because quests
 * without a session carry `{}` and hosts can enter a session by hand (title + url only).
 */
export interface InspiredBy {
  code?: string
  title?: string
  speakers?: string[]
  /** Full ISO 8601 start time with the conference's UTC offset. */
  start?: string
  room?: string
  track?: string | null
  url?: string
}

/** A talk from the event's schedule export: the `inspired_by` shape plus the session type. */
export interface SessionData extends InspiredBy {
  type?: string
}

export interface QuestData {
  id: number
  event: number
  title: string
  description: string
  target_geometry?: any
  criteria_type: CriteriaType
  validation_rules: Record<string, any>
  points_reward: number
  is_active: boolean
  inspired_by?: InspiredBy
  window_start?: string | null
  window_end?: string | null
  /** Read-only: contributions needed to complete, from validation_rules.target_count (min 1). */
  target_count?: number
  created_at: string
}

export interface LeaderboardEntry {
  id: number
  name: string
  score: number
  member_count: number
  completed_quests: number
}

/** One row per quest of the event; quests the team has not started have count 0. */
export interface QuestProgressData {
  quest: number
  quest_title: string
  count: number
  target_count: number
  points_reward: number
  completed_at: string | null
  points_awarded: boolean
  /** Points the team holds from the quest: completion plus value-scoring buckets and bonus. */
  awarded_points?: number
  /** Value-scoring buckets found (bucket starts, e.g. [1920, 1950] for decades). */
  buckets?: number[]
  /** The team's extreme verified value on a value-scoring quest (null when none yet). */
  best_value?: number | null
}

/** One team's row in GET /quests/<id>/standings/. */
export interface QuestStandingRow {
  team: number
  team_name: string
  awarded_points: number
  buckets: number[]
  best_value: number | null
  verified_count: number
}

/** GET /quests/<id>/standings/: teams by points held, and who holds the extreme value. */
export interface QuestStandings {
  quest: number
  standings: QuestStandingRow[]
  /** The extreme value for the quest's extreme_bonus; null without a bonus or a value yet. */
  extreme_value: number | null
  /** Team(s) holding extreme_value (ties share the bonus). */
  extreme_holder_team_ids: number[]
}

/** Check-in status for one location_checkin quest, as reported with a location ping. */
export interface PingCheckin {
  quest: number
  quest_title: string
  status: 'in_range' | 'verified'
  distance_m?: number
}

/**
 * A participant's recorded check-in, from GET /locations/checkins/. Only `status === 'verified'`
 * counts as checked in: 'pending' is still dwelling, 'revoked' was un-verified by a host.
 */
export interface CheckinData {
  quest: number | null
  quest_title?: string | null
  status: 'verified' | 'pending' | 'revoked'
  first_seen?: string | null
  last_seen?: string | null
  ping_count?: number | null
  distance_m?: number | null
  radius_m?: number | null
  /** Dwell time the quest required when the check-in was recorded (0 = immediately). */
  min_minutes?: number | null
  verified_at?: string | null
}

/**
 * Error carrying the HTTP status so callers can tell e.g. 400 from 502, plus DRF's per-field
 * messages ({field: [messages]}) when the server sent them, so forms can show them per field.
 */
export class ApiError extends Error {
  status: number
  fields: Record<string, string[]>
  constructor(message: string, status: number, fields: Record<string, string[]> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fields = fields
  }
}

/** Per-platform counters in a trigger_harvest response (see documentation/harvesters.md). */
export interface HarvestPlatformStats {
  harvested?: number
  created?: number
  updated?: number
  matched?: number
  errors?: number
}

export interface HarvestResult {
  message: string
  /** One entry per platform that ran, plus summary/warnings/event/found/dry_run. */
  stats: Record<string, any>
}

export interface LocationPingData {
  id: number
  event: number
  user_identifier: string
  display_name: string
  team: number | null
  team_name: string | null
  longitude: number
  latitude: number
  visibility: 'nobody' | 'team' | 'quest'
  is_foreground: boolean
  recorded_at: string
  /** Present on ping responses once the check-in matcher runs; absent on older servers. */
  checkins?: PingCheckin[]
}

export type SubmissionPlatform =
  | 'osm'
  | 'commons'
  | 'wikidata'
  | 'ohm'
  | 'osm_notes'
  | 'checkin'
  | 'github'
  | 'panoramax'

export interface SubmissionData {
  id: number
  event: number
  quest: number | null
  team: number | null
  team_name?: string
  quest_title?: string | null
  platform: SubmissionPlatform
  platform_display?: string
  external_id: string
  author_username: string
  external_url: string
  diff_payload: Record<string, any>
  is_verified: boolean
  verified_by_username: string | null
  verified_at: string | null
  /** Distinct contributions this submission counts for toward a quest's target_count. */
  element_count?: number
  /** When the contribution happened on the external platform (created_at is harvest time). */
  contributed_at?: string | null
  /** Value read for a value-scoring quest (e.g. a stamp's year); hosts can correct it. */
  extracted_value?: number | null
  created_at: string
}

/** Optional parts of a verify call. */
export interface VerifyOptions {
  /** true (the default) verifies, false puts the submission back to pending. */
  isVerified?: boolean
  /** A host's correction of a value-scoring quest's value; null clears it. Omit to keep it. */
  extractedValue?: number | null
}

/** Reads a JSON error body defensively; returns {} when the body is not JSON. */
const readError = async (res: Response): Promise<Record<string, any>> => {
  try {
    return await res.json()
  } catch {
    return {}
  }
}

/** DRF returns {field: [messages]}; surface the first field error as "field: message". */
const fieldErrorDetail = async (res: Response, fallback: string): Promise<string> => {
  const err = await readError(res)
  const first = Object.entries(err)[0]
  return first ? `${first[0]}: ${([] as any[]).concat(first[1]).join(' ')}` : fallback
}

/** Normalises a DRF error body to {field: [messages]}, ignoring non-list/non-string values. */
const fieldErrors = (body: Record<string, any>): Record<string, string[]> => {
  const out: Record<string, string[]> = {}
  for (const [field, value] of Object.entries(body)) {
    const messages = ([] as any[]).concat(value).filter((m) => typeof m === 'string')
    if (messages.length) out[field] = messages
  }
  return out
}

/** Throws an ApiError carrying the body's field errors; the message is the first "field: message". */
const throwWithFields = async (res: Response, fallback: string): Promise<never> => {
  const fields = fieldErrors(await readError(res))
  const first = Object.entries(fields)[0]
  throw new ApiError(first ? `${first[0]}: ${first[1].join(' ')}` : fallback, res.status, fields)
}

const API_BASE = '/api'

/** Total of a paginated list endpoint, from the `count` on its first page (no further pages fetched). */
const countOf = async (path: string): Promise<number> => {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) throw new ApiError(`Failed to count ${path}`, res.status)
  const data = await res.json()
  return typeof data.count === 'number' ? data.count : (Array.isArray(data) ? data.length : 0)
}


export const api = {
  // Events API
  async getEvents(): Promise<EventData[]> {
    const res = await fetch(`${API_BASE}/events/`)
    if (!res.ok) throw new Error('Failed to fetch events')
    const data = await res.json()
    return data.results || data
  },

  async getEvent(id: number | string): Promise<EventData> {
    const res = await fetch(`${API_BASE}/events/${id}/`)
    if (!res.ok) throw new Error(`Failed to fetch event ${id}`)
    return res.json()
  },

  async getEventGeoJSON(id: number | string): Promise<any> {
    const res = await fetch(`${API_BASE}/events/${id}/geojson/`)
    if (!res.ok) throw new Error(`Failed to fetch event GeoJSON ${id}`)
    return res.json()
  },

  /** Creates an event; a 400 throws ApiError whose `fields` hold the per-field messages. */
  async createEvent(event: Partial<EventData>): Promise<EventData> {
    const res = await fetch(`${API_BASE}/events/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event)
    })
    if (!res.ok) await throwWithFields(res, 'Failed to create event')
    return res.json()
  },

  /** PATCHes any subset of an event's writable fields (e.g. just `is_active`). */
  async updateEvent(eventId: number | string, changes: Partial<EventData>): Promise<EventData> {
    const res = await fetch(`${API_BASE}/events/${eventId}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changes)
    })
    if (!res.ok) await throwWithFields(res, 'Failed to update event')
    return res.json()
  },

  /** Number of quests of the event, active or not. */
  async countQuests(eventId: number | string): Promise<number> {
    return countOf(`/quests/?event=${eventId}`)
  },

  /** Number of teams of the event. */
  async countTeams(eventId: number | string): Promise<number> {
    return countOf(`/teams/?event=${eventId}`)
  },

  /** Teams of the event ranked by score (descending). */
  async getLeaderboard(eventId: number | string): Promise<LeaderboardEntry[]> {
    const res = await fetch(`${API_BASE}/events/${eventId}/leaderboard/`)
    if (!res.ok) throw new ApiError('Failed to fetch leaderboard', res.status)
    return res.json()
  },

  /**
   * Talks from the event's schedule export. Throws ApiError with status 400 when the
   * event has no schedule_url and 502 when the schedule could not be fetched.
   */
  async getSessions(eventId: number | string): Promise<SessionData[]> {
    const res = await fetch(`${API_BASE}/events/${eventId}/sessions/`)
    if (!res.ok) {
      const err = await readError(res)
      throw new ApiError(err.error || err.detail || 'Failed to fetch sessions', res.status)
    }
    return res.json()
  },

  // Teams API
  async getTeams(eventId: number | string): Promise<TeamData[]> {
    const res = await fetch(`${API_BASE}/teams/?event=${eventId}`)
    if (!res.ok) throw new Error('Failed to fetch teams')
    const data = await res.json()
    return data.results || data
  },

  async createTeam(eventId: number | string, name: string): Promise<TeamData> {
    const res = await fetch(`${API_BASE}/teams/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event: eventId, name })
    })
    if (!res.ok) {
      const err = await readError(res)
      // A duplicate name comes back as non_field_errors (unique per event)
      throw new Error(err.name?.[0] || err.non_field_errors?.[0] || 'Failed to create team')
    }
    return res.json()
  },

  /**
   * Joins a team by code. All three usernames are always sent, trimmed, with '' for blank:
   * the API clears a username on empty string and keeps it only when the key is omitted,
   * so omitting blanks would make a cleared username impossible to remove server-side.
   * JoinTeamView prefills the fields from localStorage, so unchanged values are resent as-is.
   */
  async joinTeam(
    joinCode: string,
    userIdentifier: string,
    displayName: string,
    usernames: PlatformUsernames = {}
  ): Promise<{ message: string; team: TeamData; membership: TeamMembershipData }> {
    const usernameFields: Required<PlatformUsernames> = {
      osm_username: (usernames.osm_username ?? '').trim(),
      wikimedia_username: (usernames.wikimedia_username ?? '').trim(),
      github_username: (usernames.github_username ?? '').trim()
    }
    const res = await fetch(`${API_BASE}/teams/join/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        join_code: joinCode,
        user_identifier: userIdentifier,
        display_name: displayName,
        ...usernameFields
      })
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.error || 'Failed to join team')
    }
    return res.json()
  },

  /** The team's progress on every quest of its event. */
  async getTeamProgress(teamId: number | string): Promise<QuestProgressData[]> {
    const res = await fetch(`${API_BASE}/teams/${teamId}/progress/`)
    if (!res.ok) throw new ApiError('Failed to fetch team progress', res.status)
    return res.json()
  },

  /** Every team's standing on one quest, and who holds its extreme value (value-scoring quests). */
  async getQuestStandings(questId: number | string): Promise<QuestStandings> {
    const res = await fetch(`${API_BASE}/quests/${questId}/standings/`)
    if (!res.ok) throw new ApiError('Failed to fetch quest standings', res.status)
    return res.json()
  },

  // Quests API
  async getQuests(eventId: number | string): Promise<QuestData[]> {
    const res = await fetch(`${API_BASE}/quests/?event=${eventId}`)
    if (!res.ok) throw new Error('Failed to fetch quests')
    const data = await res.json()
    return data.results || data
  },

  async createQuest(quest: Partial<QuestData>): Promise<QuestData> {
    const res = await fetch(`${API_BASE}/quests/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(quest)
    })
    if (!res.ok) throw new ApiError(await fieldErrorDetail(res, 'Failed to create quest'), res.status)
    return res.json()
  },

  /** PATCHes any subset of a quest's writable fields; the server keeps the target inside the event. */
  async updateQuest(questId: number | string, changes: Partial<QuestData>): Promise<QuestData> {
    const res = await fetch(`${API_BASE}/quests/${questId}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changes)
    })
    if (!res.ok) throw new ApiError(await fieldErrorDetail(res, 'Failed to update quest'), res.status)
    return res.json()
  },

  async deleteQuest(questId: number | string): Promise<void> {
    const res = await fetch(`${API_BASE}/quests/${questId}/`, { method: 'DELETE' })
    if (!res.ok) throw new ApiError('Failed to delete quest', res.status)
  },

  // Locations API
  async pingLocation(payload: {
    event: number | string
    user_identifier: string
    display_name?: string
    longitude: number
    latitude: number
    visibility?: 'nobody' | 'team' | 'quest'
    is_foreground?: boolean
  }): Promise<LocationPingData> {
    const res = await fetch(`${API_BASE}/locations/ping/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!res.ok) throw new Error('Failed to send location ping')
    return res.json()
  },

  async getActiveLocations(eventId: number | string, userIdentifier: string): Promise<LocationPingData[]> {
    const res = await fetch(`${API_BASE}/locations/active/?event=${eventId}&user_identifier=${encodeURIComponent(userIdentifier)}`)
    if (!res.ok) throw new Error('Failed to fetch active locations')
    return res.json()
  },

  /**
   * The participant's check-ins for an event. Returns [] when the server does not
   * have the endpoint yet (404) so callers can treat check-ins as optional.
   */
  async getCheckins(eventId: number | string, userIdentifier: string): Promise<CheckinData[]> {
    const res = await fetch(`${API_BASE}/locations/checkins/?event=${eventId}&user_identifier=${encodeURIComponent(userIdentifier)}`)
    if (res.status === 404) return []
    if (!res.ok) throw new ApiError('Failed to fetch check-ins', res.status)
    const data = await res.json()
    return data.results || data
  },

  // Submissions API
  async getSubmissions(eventId: number | string): Promise<SubmissionData[]> {
    const res = await fetch(`${API_BASE}/submissions/?event=${eventId}`)
    if (!res.ok) throw new Error('Failed to fetch submissions')
    const data = await res.json()
    return data.results || data
  },

  /** Number of submissions of the event, optionally only verified (true) or pending (false). */
  async countSubmissions(eventId: number | string, isVerified?: boolean): Promise<number> {
    const filter = isVerified === undefined ? '' : `&is_verified=${isVerified}`
    return countOf(`/submissions/?event=${eventId}${filter}`)
  },

  /**
   * Runs a harvest for the event now and returns {message, stats}. A 404 (event missing or
   * inactive) or 400 throws ApiError with the server's message.
   */
  async triggerHarvest(eventId: number | string): Promise<HarvestResult> {
    const res = await fetch(`${API_BASE}/submissions/trigger_harvest/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event: Number(eventId) })
    })
    if (!res.ok) {
      const err = await readError(res)
      throw new ApiError(err.error || err.detail || 'Harvest failed', res.status)
    }
    return res.json()
  },

  async verifySubmission(
    submissionId: number | string,
    verifiedByUsername: string = 'Host',
    options: VerifyOptions = {}
  ): Promise<SubmissionData> {
    const body: Record<string, any> = { verified_by_username: verifiedByUsername }
    if (options.isVerified !== undefined) body.is_verified = options.isVerified
    if ('extractedValue' in options) body.extracted_value = options.extractedValue ?? null
    const res = await fetch(`${API_BASE}/submissions/${submissionId}/verify/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
    if (!res.ok) throw new Error('Failed to verify submission')
    return res.json()
  }
}
