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
  is_active: boolean
  created_at: string
}

export interface TeamMembershipData {
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

export interface QuestData {
  id: number
  event: number
  title: string
  description: string
  target_geometry?: any
  criteria_type: 'osm_tags' | 'wikimedia_commons' | 'wikidata_entry'
  validation_rules: Record<string, any>
  points_reward: number
  is_active: boolean
  created_at: string
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
}

export interface SubmissionData {
  id: number
  event: number
  quest: number | null
  team: number | null
  team_name?: string
  quest_title?: string | null
  platform: 'osm' | 'commons' | 'wikidata'
  external_id: string
  author_username: string
  external_url: string
  diff_payload: Record<string, any>
  is_verified: boolean
  verified_by_username: string | null
  verified_at: string | null
  created_at: string
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

  async joinTeam(joinCode: string, userIdentifier: string, displayName: string): Promise<{ message: string; team: TeamData; membership: TeamMembershipData }> {
    const res = await fetch(`${API_BASE}/teams/join/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        join_code: joinCode,
        user_identifier: userIdentifier,
        display_name: displayName
      })
    })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.error || 'Failed to join team')
    }
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
      const err = await res.json()
      throw new Error(err.target_geometry || err.title || 'Failed to create quest')
    }
    return res.json()
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
