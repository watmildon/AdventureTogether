/**
 * Display helpers for value-scoring quests (`validation_rules.scoring`, see
 * documentation/quest_types.md): points per distinct bucket of values (e.g. +5 per decade of
 * sidewalk stamp years) and a bonus for the team holding the extreme value (e.g. the oldest).
 *
 * Kept free of Vue so it can be unit-tested directly; the builder's form side lives in
 * questRules.ts.
 */

import type { QuestData } from '../api'

export type ValueKind = 'year' | 'number'
export type ExtremeDirection = 'min' | 'max'

/** A quest's scoring rule, normalised for display. */
export interface QuestScoring {
  kind: ValueKind
  /** Bucket width (10 = decades for years); null when there are no per-bucket points. */
  bucketSize: number | null
  bucketPoints: number
  direction: ExtremeDirection
  /** null when the quest has no extreme bonus. */
  bonusPoints: number | null
}

const num = (value: unknown): number | null => {
  const n = Number(value)
  return value !== null && value !== undefined && value !== '' && Number.isFinite(n) ? n : null
}

/** The quest's scoring rule, or null when it does not score values. */
export function questScoring(quest: Pick<QuestData, 'validation_rules'> | null | undefined): QuestScoring | null {
  const scoring = quest?.validation_rules?.scoring
  if (!scoring || typeof scoring !== 'object') return null
  const size = num(scoring.per_bucket?.size)
  const bonus = scoring.extreme_bonus && typeof scoring.extreme_bonus === 'object' ? scoring.extreme_bonus : null
  return {
    kind: scoring.value?.kind === 'number' ? 'number' : 'year',
    bucketSize: size !== null && size > 0 ? size : null,
    bucketPoints: num(scoring.per_bucket?.points) ?? 0,
    direction: bonus?.direction === 'max' ? 'max' : 'min',
    bonusPoints: bonus ? num(bonus.points) ?? 0 : null
  }
}

/** "1923" for a year, "1,250" or "3.5" for a number. */
export function formatValue(value: number | null | undefined, kind: ValueKind): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return ''
  return kind === 'year' ? String(Math.round(value)) : value.toLocaleString('en-US')
}

/**
 * One bucket by its start: years in decades read "1920s"; any other bucket is a range,
 * "1900–1924" or "0–9" (inclusive for whole-number widths).
 */
export function formatBucket(start: number, size: number, kind: ValueKind): string {
  if (kind === 'year' && size === 10 && Number.isInteger(start)) return `${start}s`
  const end = Number.isInteger(size) && Number.isInteger(start) ? start + size - 1 : start + size
  return `${formatValue(start, kind)}–${formatValue(end, kind)}`
}

/** "Decades" for 10-year buckets, "Centuries" for 100, otherwise "Ranges". */
export function bucketNoun(size: number, kind: ValueKind): string {
  if (kind === 'year' && size === 10) return 'Decades'
  if (kind === 'year' && size === 100) return 'Centuries'
  return 'Ranges'
}

/** "oldest" / "newest" for years, "lowest" / "highest" for numbers. */
export function extremeWord(direction: ExtremeDirection, kind: ValueKind): string {
  if (kind === 'year') return direction === 'min' ? 'oldest' : 'newest'
  return direction === 'min' ? 'lowest' : 'highest'
}

/** "Decades found: 1920s, 1950s", or null when there is nothing to list. */
export function bucketsLine(buckets: number[] | null | undefined, scoring: QuestScoring): string | null {
  if (!scoring.bucketSize || !buckets?.length) return null
  const labels = [...buckets].sort((a, b) => a - b).map((b) => formatBucket(b, scoring.bucketSize as number, scoring.kind))
  return `${bucketNoun(scoring.bucketSize, scoring.kind)} found: ${labels.join(', ')}`
}

/** "+5 per decade, +25 for the oldest" (the rule in a few words), or '' when it adds nothing. */
export function scoringSummary(scoring: QuestScoring): string {
  const parts: string[] = []
  if (scoring.bucketSize && scoring.bucketPoints) {
    const noun = bucketNoun(scoring.bucketSize, scoring.kind)
    const unit = noun === 'Decades' ? 'decade' : noun === 'Centuries' ? 'century' : `range of ${scoring.bucketSize}`
    parts.push(`+${scoring.bucketPoints} per ${unit}`)
  }
  if (scoring.bonusPoints) parts.push(`+${scoring.bonusPoints} for the ${extremeWord(scoring.direction, scoring.kind)}`)
  return parts.join(', ')
}
