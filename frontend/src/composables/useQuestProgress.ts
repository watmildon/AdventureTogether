/**
 * Team progress and leaderboard state for an event, refreshed on a polling interval.
 *
 * Progress needs the participant's team id for this event, which JoinTeamView stores in
 * localStorage under an event-scoped key (or the ping response reports).
 * Without a team the leaderboard still loads and quests show only their targets.
 */

import { ref, computed, watch, getCurrentInstance, onUnmounted, type Ref } from 'vue'
import { api, type LeaderboardEntry, type QuestProgressData } from '../api'

/** How often the leaderboard and team progress are refreshed while the map is open. */
export const PROGRESS_POLL_MS = 30000

/**
 * The participant's team for this event, from the event-scoped record JoinTeamView writes
 * (`team_for_event_<id>`). The global `team_id` / `team_name` keys are deliberately not read:
 * they hold whichever team was joined last, possibly for another event.
 */
export function readStoredTeam(eventId: number | string): { id: number; name: string | null } | null {
  try {
    const scoped = localStorage.getItem(`team_for_event_${eventId}`)
    if (!scoped) return null
    const team = JSON.parse(scoped)
    const id = Number(team?.id)
    if (!Number.isFinite(id) || id <= 0) return null
    return { id, name: typeof team?.name === 'string' ? team.name : null }
  } catch {
    // Corrupt value: treat as no team; the ping response can still supply one
    return null
  }
}

/** Shorthand for `readStoredTeam(eventId)?.id`. */
export function readStoredTeamId(eventId: number | string): number | null {
  return readStoredTeam(eventId)?.id ?? null
}

export function useQuestProgress(eventId: number | string, teamId: Ref<number | null>) {
  const progress = ref<QuestProgressData[]>([])
  const leaderboard = ref<LeaderboardEntry[]>([])
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setInterval> | null = null

  /** Progress rows keyed by quest id for O(1) lookup from quest cards and popups. */
  const progressByQuest = computed(() => {
    const byQuest = new Map<number, QuestProgressData>()
    progress.value.forEach((row) => byQuest.set(row.quest, row))
    return byQuest
  })

  const refreshProgress = async () => {
    if (!teamId.value) {
      progress.value = []
      return
    }
    try {
      progress.value = await api.getTeamProgress(teamId.value)
    } catch {
      // Keep the last known progress; the next poll retries
    }
  }

  const refreshLeaderboard = async () => {
    try {
      leaderboard.value = await api.getLeaderboard(eventId)
      error.value = null
    } catch {
      error.value = 'Leaderboard unavailable right now.'
    }
  }

  const refresh = () => Promise.all([refreshProgress(), refreshLeaderboard()])

  const startPolling = (intervalMs: number = PROGRESS_POLL_MS) => {
    stopPolling()
    timer = setInterval(refresh, intervalMs)
  }

  const stopPolling = () => {
    if (timer) clearInterval(timer)
    timer = null
  }

  // A team id learned later (e.g. from a ping response) loads progress straight away
  watch(teamId, () => refreshProgress())

  if (getCurrentInstance()) onUnmounted(stopPolling)

  return { progress, progressByQuest, leaderboard, error, refresh, refreshProgress, refreshLeaderboard, startPolling, stopPolling }
}
