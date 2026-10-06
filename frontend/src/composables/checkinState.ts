/**
 * Maps the server's check-in statuses onto what the quest panel shows.
 *
 * Two shapes reach the client:
 *   - ping responses list the quests this ping is in range of, with status
 *     'in_range' | 'verified';
 *   - GET /locations/checkins/ lists recorded check-ins, with status
 *     'verified' | 'pending' | 'revoked'.
 * Only 'verified' counts as checked in. 'in_range' and 'pending' mean the participant is (or
 * was last seen) at the quest; when the quest needs a dwell time that is 'dwelling'. A
 * 'revoked' check-in (a host un-verified it) never shows as done.
 */

import type { CheckinData, PingCheckin, QuestData } from '../api'

export type CheckinState = 'in_range' | 'dwelling' | 'verified'
export type CheckinStates = Record<number, CheckinState>

/** Minutes a participant must stay in range, from the quest's validation_rules (0 = immediately). */
export const questMinMinutes = (quest: Pick<QuestData, 'validation_rules'> | undefined): number => {
  const minutes = Number(quest?.validation_rules?.min_minutes)
  return Number.isFinite(minutes) && minutes > 0 ? minutes : 0
}

/** The panel state for one server status, or null when nothing should show (revoked, unknown). */
export function checkinStateFor(status: string | null | undefined, minMinutes?: number | null): CheckinState | null {
  if (status === 'verified') return 'verified'
  if (status === 'in_range' || status === 'pending') return Number(minMinutes) > 0 ? 'dwelling' : 'in_range'
  return null
}

/**
 * Merges recorded check-ins (loaded once, e.g. after a reload) into the current states.
 * Verified records win; pending ones fill in only where no fresher ping state exists;
 * revoked ones add nothing.
 */
export function mergeRecordedCheckins(
  current: CheckinStates,
  rows: CheckinData[],
  minMinutesFor: (questId: number) => number = () => 0
): CheckinStates {
  const next: CheckinStates = { ...current }
  for (const row of rows) {
    if (!row || typeof row.quest !== 'number') continue
    const minMinutes = row.min_minutes ?? minMinutesFor(row.quest)
    const state = checkinStateFor(row.status, minMinutes)
    if (state === 'verified') next[row.quest] = state
    else if (state && !next[row.quest]) next[row.quest] = state
  }
  return next
}

/**
 * Applies a ping response's `checkins` list. Verified states are sticky; in-range and
 * dwelling states are replaced by what this ping reports. Returns the new states, whether
 * any quest became verified, and the check-ins seen for the first time (for a toast).
 */
export function mergePingCheckins(
  current: CheckinStates,
  list: PingCheckin[],
  minMinutesFor: (questId: number) => number = () => 0
): { next: CheckinStates; newlyVerified: boolean; firstSeen: PingCheckin[] } {
  const next: CheckinStates = {}
  for (const [id, state] of Object.entries(current)) {
    if (state === 'verified') next[Number(id)] = state
  }

  let newlyVerified = false
  const firstSeen: PingCheckin[] = []
  for (const checkin of list) {
    if (!checkin || typeof checkin.quest !== 'number') continue
    const previous = current[checkin.quest]
    if (previous === 'verified') continue
    const state = checkinStateFor(checkin.status, minMinutesFor(checkin.quest))
    if (!state) continue

    next[checkin.quest] = state
    if (state === 'verified') newlyVerified = true
    if (!previous) firstSeen.push(checkin)
  }
  return { next, newlyVerified, firstSeen }
}
