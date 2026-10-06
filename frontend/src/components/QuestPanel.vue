<script setup lang="ts">
/**
 * Participant-facing list of an event's quests: type, points, team progress, quest
 * window, the talk that inspired it, and a "Show on map" action.
 *
 * Purely presentational: EventMapView owns the data (quests, progress, check-ins)
 * and handles the map side of "Show on map".
 */
import { computed } from 'vue'
import type { QuestData, QuestProgressData } from '../api'
import { questTypeFor, formatSessionLine, formatQuestWindow } from '../composables/useQuestTypes'
import type { CheckinStates } from '../composables/checkinState'

const props = withDefaults(defineProps<{
  quests: QuestData[]
  /** Team progress keyed by quest id; empty when the participant has no team. */
  progressByQuest?: Map<number, QuestProgressData>
  /** True when the participant has a team, so missing progress means 0 rather than unknown. */
  hasTeam?: boolean
  /** Check-in state per quest id from pings / the check-ins endpoint (see checkinState.ts). */
  checkins?: CheckinStates
}>(), {
  progressByQuest: () => new Map(),
  hasTeam: false,
  checkins: () => ({})
})

const emit = defineEmits<{ (e: 'show-on-map', quest: QuestData): void }>()

/** Everything a card renders, derived once per quest. */
const cards = computed(() =>
  props.quests.map((quest) => {
    const row = props.progressByQuest.get(quest.id)
    const target = row?.target_count ?? quest.target_count ?? 1
    const count = row?.count ?? 0
    return {
      quest,
      type: questTypeFor(quest.criteria_type),
      session: formatSessionLine(quest.inspired_by),
      window: formatQuestWindow(quest.window_start, quest.window_end),
      count,
      target,
      complete: Boolean(row && (row.completed_at || row.count >= row.target_count)),
      // Capped so a team that overshoots the target does not overflow the bar
      percent: Math.min(100, Math.round((count / Math.max(target, 1)) * 100)),
      checkin: props.checkins[quest.id]
    }
  })
)
</script>

<template>
  <div class="quest-panel">
    <p v-if="quests.length === 0" class="empty">No quests published for this event yet.</p>

    <ul v-else class="quest-list">
      <li
        v-for="card in cards"
        :key="card.quest.id"
        :class="['quest-card', { complete: card.complete }]"
        :style="{ '--type-color': `var(${card.type.colorToken})` }"
        :data-quest-id="card.quest.id"
      >
        <div class="quest-top">
          <span class="type-badge">{{ card.type.icon }} {{ card.type.shortLabel }}</span>
          <span class="points">{{ card.quest.points_reward }} pts</span>
          <span v-if="card.complete" class="state state-done">✓ Done</span>
          <span v-else-if="card.checkin === 'verified'" class="state state-done">✓ Checked in</span>
          <span v-else-if="card.checkin === 'in_range'" class="state state-here">📍 You're here</span>
          <span v-else-if="card.checkin === 'dwelling'" class="state state-here">📍 You're here, stay a few minutes</span>
        </div>

        <h4 class="quest-title">{{ card.quest.title }}</h4>

        <div class="quest-progress">
          <template v-if="hasTeam">
            <div class="bar" role="progressbar" :aria-valuenow="card.count" aria-valuemin="0" :aria-valuemax="card.target">
              <div class="bar-fill" :style="{ width: `${card.percent}%` }"></div>
            </div>
            <span class="progress-text">{{ card.count }}/{{ card.target }}</span>
          </template>
          <span v-else class="progress-text">Target: {{ card.target }}</span>
        </div>

        <p v-if="card.window" class="quest-meta">🕒 {{ card.window }}</p>

        <p v-if="card.session" class="quest-meta inspired">
          Inspired by:
          <a v-if="card.session.url" :href="card.session.url" target="_blank" rel="noopener">{{ card.session.title }}</a>
          <span v-else>{{ card.session.title }}</span>
          <span v-if="card.session.details"> — {{ card.session.details }}</span>
        </p>

        <div class="quest-actions">
          <span class="help-app">Use: {{ card.type.helpApp }}</span>
          <button
            v-if="card.quest.target_geometry"
            type="button"
            class="btn btn-outline show-btn"
            @click="emit('show-on-map', card.quest)"
          >
            Show on map
          </button>
          <span v-else class="help-app">Anywhere in the event area</span>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.empty {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.quest-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.quest-card {
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--type-color, var(--color-primary));
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  background-color: var(--color-bg-surface);
}

.quest-card.complete {
  background-color: var(--color-success-light);
}

.quest-top {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-xs);
}

.type-badge {
  font-weight: var(--font-weight-semibold);
  color: var(--type-color, var(--color-primary));
}

.points {
  color: var(--color-text-muted);
}

.state {
  margin-left: auto;
  font-weight: var(--font-weight-semibold);
}

.state-done {
  color: var(--color-success);
}

.state-here {
  color: var(--color-warning);
}

.quest-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  line-height: 1.3;
}

.quest-progress {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.bar {
  flex: 1;
  height: 6px;
  border-radius: var(--radius-full);
  background-color: var(--color-bg-subtle);
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background-color: var(--type-color, var(--color-primary));
}

.complete .bar-fill {
  background-color: var(--color-success);
}

.progress-text {
  font-size: var(--font-size-xs);
  font-variant-numeric: tabular-nums;
  color: var(--color-text-muted);
}

.quest-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.inspired {
  font-style: italic;
}

.quest-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-2);
}

.help-app {
  font-size: 0.7rem;
  color: var(--color-text-subtle);
}

.show-btn {
  font-size: var(--font-size-xs);
  padding: var(--space-1) var(--space-2);
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
