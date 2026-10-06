<script setup lang="ts">
/**
 * Ranked team list. Used in the map sidebar (top 5, with the participant's team
 * highlighted) and compactly on home page event cards (top 3).
 */
import { computed } from 'vue'
import type { LeaderboardEntry } from '../api'

const props = withDefaults(defineProps<{
  entries: LeaderboardEntry[]
  limit?: number
  highlightTeamId?: number | null
  compact?: boolean
}>(), {
  limit: 5,
  highlightTeamId: null,
  compact: false
})

const top = computed(() => props.entries.slice(0, props.limit))

/** The participant's team when it ranks below the visible cut-off, shown as a trailing row. */
const ownBelowCut = computed(() => {
  if (!props.highlightTeamId) return null
  const index = props.entries.findIndex((e) => e.id === props.highlightTeamId)
  return index >= props.limit ? { entry: props.entries[index], rank: index + 1 } : null
})
</script>

<template>
  <ol :class="['leaderboard', { compact }]">
    <li
      v-for="(entry, index) in top"
      :key="entry.id"
      :class="['leaderboard-row', { own: entry.id === highlightTeamId }]"
    >
      <span class="rank">{{ index + 1 }}</span>
      <span class="name">
        {{ entry.name }}
        <span v-if="entry.id === highlightTeamId" class="you">(you)</span>
      </span>
      <span v-if="!compact" class="meta">{{ entry.completed_quests }} done</span>
      <span class="score">{{ entry.score }} pts</span>
    </li>
    <li v-if="ownBelowCut" class="leaderboard-row own">
      <span class="rank">{{ ownBelowCut.rank }}</span>
      <span class="name">{{ ownBelowCut.entry.name }} <span class="you">(you)</span></span>
      <span v-if="!compact" class="meta">{{ ownBelowCut.entry.completed_quests }} done</span>
      <span class="score">{{ ownBelowCut.entry.score }} pts</span>
    </li>
  </ol>
</template>

<style scoped>
.leaderboard {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.leaderboard-row {
  display: grid;
  grid-template-columns: 1.5rem 1fr auto auto;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
}

.compact .leaderboard-row {
  grid-template-columns: 1.25rem 1fr auto;
  font-size: var(--font-size-xs);
  padding: 2px var(--space-2);
}

.leaderboard-row.own {
  background-color: var(--color-primary-light);
  outline: 1px solid var(--color-primary-border);
}

.rank {
  color: var(--color-text-muted);
  font-weight: var(--font-weight-semibold);
  text-align: right;
}

.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.you {
  color: var(--color-primary);
  font-size: var(--font-size-xs);
}

.meta {
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
}

.score {
  font-weight: var(--font-weight-semibold);
  font-variant-numeric: tabular-nums;
}
</style>
