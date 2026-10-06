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
}

/** Check-in status for one location_checkin quest, as reported with a location ping. */
export interface PingCheckin {
  quest: number
  quest_title: string
  status: 'in_range' | 'verified'
  distance_m?: number
}

/**
 * A participant's recorded check-in. The endpoint returns check-in submissions, so only
 * `quest` is relied on; the other fields are read when present.
 */
export interface CheckinData {
  id?: number
  quest: number | null
  quest_title?: string | null
  is_verified?: boolean
  contributed_at?: string | null
  created_at?: string
}

/** Error carrying the HTTP status so callers can tell e.g. 400 from 502. */
export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
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
  created_at: string
}

/** Reads a JSON error body defensively; returns {} when the body is not JSON. */
const readError = async (res: Response): Promise<Record<string, any>> => {
  try {
    return await res.json()
  } catch {
    return {}
  }
}

const API_BASE = '/api'

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

  async createEvent(event: Partial<EventData>): Promise<EventData> {
    const res = await fetch(`${API_BASE}/events/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event)
    })
    if (!res.ok) throw new Error('Failed to create event')
    return res.json()
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
      const err = await res.json()
      throw new Error(err.name?.[0] || 'Failed to create team')
    }
    return res.json()
  },

  /**
   * Joins a team by code. Usernames are optional; blank ones are left out so a
   * re-join does not clear values stored earlier (the API clears on empty string).
   */
  async joinTeam(
    joinCode: string,
    userIdentifier: string,
    displayName: string,
    usernames: PlatformUsernames = {}
  ): Promise<{ message: string; team: TeamData; membership: TeamMembershipData }> {
    const optional: PlatformUsernames = {}
    for (const [key, value] of Object.entries(usernames) as [keyof PlatformUsernames, string | undefined][]) {
      if (value && value.trim()) optional[key] = value.trim()
    }
    const res = await fetch(`${API_BASE}/teams/join/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        join_code: joinCode,
        user_identifier: userIdentifier,
        display_name: displayName,
        ...optional
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
    if (!res.ok) {
      const err = await readError(res)
      // DRF returns {field: [messages]}; surface the first field error we can find
      const first = Object.entries(err)[0]
      const detail = first ? `${first[0]}: ${([] as any[]).concat(first[1]).join(' ')}` : null
      throw new Error(detail || 'Failed to create quest')
    }
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

  async verifySubmission(submissionId: number | string, verifiedByUsername: string = 'Host'): Promise<SubmissionData> {
    const res = await fetch(`${API_BASE}/submissions/${submissionId}/verify/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ verified_by_username: verifiedByUsername })
    })
    if (!res.ok) throw new Error('Failed to verify submission')
    return res.json()
  }
}
