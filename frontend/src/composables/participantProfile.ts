/**
 * The participant's profile and tool list, kept in localStorage on their device (there is no
 * account yet). The landing page edits it; JoinTeamView, the map and geolocation read it.
 *
 * The keys are the ones the app already used before the landing page existed, so profiles
 * typed into the old join form carry over.
 */

import type { PlatformUsernames } from '../api'
import type { VisibilityTier } from './useGeolocation'
import { TOOLS, type ToolId } from './useQuestTypes'

export const PROFILE_KEYS = {
  id: 'participant_id',
  name: 'participant_name',
  visibility: 'privacy_visibility',
  tools: 'participant_tools'
} as const

/** Platform username field -> localStorage key. */
export const USERNAME_STORAGE_KEYS: Record<keyof PlatformUsernames, string> = {
  osm_username: 'participant_osm_username',
  wikimedia_username: 'participant_wikimedia_username',
  github_username: 'participant_github_username'
}

export interface ParticipantProfile {
  displayName: string
  usernames: Required<PlatformUsernames>
  visibility: VisibilityTier
}

const VISIBILITY_TIERS: VisibilityTier[] = ['nobody', 'team', 'quest']

/** Returns the device's participant id, generating and storing one the first time. */
export function ensureParticipantId(): string {
  const existing = localStorage.getItem(PROFILE_KEYS.id)
  if (existing) return existing
  const generated = `user-${Math.random().toString(36).substring(2, 9)}`
  localStorage.setItem(PROFILE_KEYS.id, generated)
  return generated
}

export function readProfile(): ParticipantProfile {
  const stored = localStorage.getItem(PROFILE_KEYS.visibility) as VisibilityTier | null
  return {
    displayName: localStorage.getItem(PROFILE_KEYS.name) || '',
    usernames: {
      osm_username: localStorage.getItem(USERNAME_STORAGE_KEYS.osm_username) || '',
      wikimedia_username: localStorage.getItem(USERNAME_STORAGE_KEYS.wikimedia_username) || '',
      github_username: localStorage.getItem(USERNAME_STORAGE_KEYS.github_username) || ''
    },
    // 'team' is the map's default sharing tier (see useGeolocation)
    visibility: stored && VISIBILITY_TIERS.includes(stored) ? stored : 'team'
  }
}

/**
 * Saves the display name and usernames (trimmed; a blank username removes its key so it is not
 * resent as a stale value). Returns the trimmed usernames, ready for the join call.
 */
export function saveIdentity(displayName: string, usernames: PlatformUsernames): Required<PlatformUsernames> {
  localStorage.setItem(PROFILE_KEYS.name, displayName.trim())
  const trimmed: Required<PlatformUsernames> = {
    osm_username: (usernames.osm_username ?? '').trim(),
    wikimedia_username: (usernames.wikimedia_username ?? '').trim(),
    github_username: (usernames.github_username ?? '').trim()
  }
  for (const [field, key] of Object.entries(USERNAME_STORAGE_KEYS) as [keyof PlatformUsernames, string][]) {
    if (trimmed[field]) localStorage.setItem(key, trimmed[field])
    else localStorage.removeItem(key)
  }
  return trimmed
}

export function saveVisibility(tier: VisibilityTier): void {
  localStorage.setItem(PROFILE_KEYS.visibility, tier)
}

const KNOWN_TOOLS = new Set<string>(TOOLS.map((tool) => tool.id))

/** The ticked tools; ignores unknown ids and corrupt values. */
export function readTools(): ToolId[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(PROFILE_KEYS.tools) || '[]')
    return Array.isArray(parsed) ? (parsed.filter((id) => KNOWN_TOOLS.has(id)) as ToolId[]) : []
  } catch {
    return []
  }
}

export function saveTools(tools: readonly ToolId[]): void {
  localStorage.setItem(PROFILE_KEYS.tools, JSON.stringify([...new Set(tools)]))
}
