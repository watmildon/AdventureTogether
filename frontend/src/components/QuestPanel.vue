<script setup lang="ts">
/**
 * Participant-facing list of an event's quests: type, points, team progress, quest
 * window, the talk that inspired it, and a "Show on map" action. Value-scoring quests
 * also show the points the team holds, the buckets it has found (e.g. decades), its best
 * value, and whether it holds the extreme bonus.
 *
 * Purely presentational: EventMapView owns the data (quests, progress, standings,
 * check-ins) and handles the map side of "Show on map".
 */
import { ref, computed } from 'vue'
import type { QuestData, QuestProgressData, QuestStandings } from '../api'
import { questTypeFor, formatSessionLine, formatQuestWindow, canDoQuest, toolsNeededText } from '../composables/useQuestTypes'
import type { CheckinStates } from '../composables/checkinState'
import { questScoring, scoringSummary, bucketsLine, formatValue, extremeWord, type QuestScoring } from '../composables/valueScoring'

const props = withDefaults(defineProps<{
  quests: QuestData[]
  /** Team progress keyed by quest id; empty when the participant has no team. */
  progressByQuest?: Map<number, QuestProgressData>
  /** True when the participant has a team, so missing progress means 0 rather than unknown. */
  hasTeam?: boolean
  /** Check-in state per quest id from pings / the check-ins endpoint (see checkinState.ts). */
  checkins?: CheckinStates
  /** Tools the participant ticked on the landing page (`participant_tools`). */
  tools?: readonly string[]
  /** Standings of value-scoring quests keyed by quest id (who holds the extreme bonus). */
  standingsByQuest?: Map<number, QuestStandings>
  /** The participant's team, to tell whether it holds a bonus. */
  teamId?: number | null
}>(), {
  progressByQuest: () => new Map(),
  hasTeam: false,
  checkins: () => ({}),
  tools: () => [],
  standingsByQuest: () => new Map(),
  teamId: null
})

const emit = defineEmits<{ (e: 'show-on-map', quest: QuestData): void }>()

/**
 * "Only quests I can do": on by default once the participant has ticked any tool. With no
 * tools ticked we cannot tell what they can do, so everything shows (with "Needs: ..." lines).
 */
const onlyDoable = ref(props.tools.length > 0)

/** The value-scoring lines of a card, or null for a quest that does not score values. */
const scoringCard = (quest: QuestData, scoring: QuestScoring | null, row?: QuestProgressData) => {
  if (!scoring) return null
  const standings = props.standingsByQuest.get(quest.id)
  const word = extremeWord(scoring.direction, scoring.kind)
  const extreme = standings?.extreme_value ?? null
  const holdsBonus = Boolean(props.teamId && standings?.extreme_holder_team_ids.includes(props.teamId))
  let bonusText: string | null = null
  if (scoring.bonusPoints !== null && standings && extreme !== null) {
    const holders = standings.standings
      .filter((s) => standings.extreme_holder_team_ids.includes(s.team))
      .map((s) => s.team_name)
    bonusText = holdsBonus
      ? `🏆 Your team holds the ${word} (${formatValue(extreme, scoring.kind)}): +${scoring.bonusPoints}`
      : `${word[0].toUpperCase()}${word.slice(1)} so far: ${formatValue(extreme, scoring.kind)}, held by ${holders.join(', ') || 'another team'}`
  }
  return {
    summary: scoringSummary(scoring),
    awarded: row?.awarded_points ?? 0,
    buckets: bucketsLine(row?.buckets, scoring),
    best: row?.best_value != null ? `Your ${word}: ${formatValue(row.best_value, scoring.kind)}` : null,
    holdsBonus,
    bonusText
  }
}

/** Everything a card renders, derived once per quest. */
const allCards = computed(() =>
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
      checkin: props.checkins[quest.id],
      doable: canDoQuest(quest.criteria_type, props.tools),
      needs: toolsNeededText(quest.criteria_type),
      // osm_tags quests with action "create" only count elements the participant adds
      newOnly: quest.criteria_type === 'osm_tags' && quest.validation_rules?.action === 'create',
      scoring: scoringCard(quest, questScoring(quest), row)
    }
  })
)

const cards = computed(() => (onlyDoable.value ? allCards.value.filter((card) => card.doable) : allCards.value))
const hiddenCount = computed(() => allCards.value.length - cards.value.length)
</script>

<template>
  <div class="quest-panel">
    <p v-if="quests.length === 0" class="empty">No quests published for this event yet.</p>

    <template v-else>
      <label class="doable-toggle">
        <input v-model="onlyDoable" type="checkbox" />
        Only quests I can do
      </label>
      <p v-if="onlyDoable && hiddenCount > 0" class="hidden-note">
        {{ hiddenCount }} quest{{ hiddenCount === 1 ? '' : 's' }} hidden: they need tools you have not ticked.
        <a href="/">Update your tools</a>
      </p>
      <p v-if="!onlyDoable && tools.length === 0" class="hidden-note">
        Tick the <a href="/">tools you have</a> to see only the quests you can do.
      </p>

      <ul class="quest-list">
        <li
          v-for="card in cards"
          :key="card.quest.id"
          :class="['quest-card', { complete: card.complete, 'not-doable': !card.doable }]"
          :style="{ '--type-color': `var(${card.type.colorToken})` }"
          :data-quest-id="card.quest.id"
        >
          <div class="quest-top">
            <span class="type-badge">{{ card.type.icon }} {{ card.type.shortLabel }}</span>
            <span class="points">
              {{ card.quest.points_reward }} pts<template v-if="card.scoring?.summary">, {{ card.scoring.summary }}</template>
            </span>
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

          <div v-if="card.scoring && (hasTeam || card.scoring.bonusText)" class="scoring">
            <p v-if="hasTeam" class="quest-meta scoring-points">
              <strong>{{ card.scoring.awarded }} pts</strong> held<template v-if="card.scoring.best"> · {{ card.scoring.best }}</template>
            </p>
            <p v-if="hasTeam && card.scoring.buckets" class="quest-meta scoring-buckets">{{ card.scoring.buckets }}</p>
            <p v-if="card.scoring.bonusText" :class="['quest-meta', 'scoring-bonus', { held: card.scoring.holdsBonus }]">
              {{ card.scoring.bonusText }}
            </p>
          </div>

          <p v-if="!card.doable" class="quest-meta needs">Needs: {{ card.needs }}</p>

          <p v-if="card.window" class="quest-meta">🕒 {{ card.window }}</p>

          <p v-if="card.session" class="quest-meta inspired">
            Inspired by:
            <a v-if="card.session.url" :href="card.session.url" target="_blank" rel="noopener">{{ card.session.title }}</a>
            <span v-else>{{ card.session.title }}</span>
            <span v-if="card.session.details"> — {{ card.session.details }}</span>
          </p>

          <div class="quest-actions">
            <span class="help-app">Use: {{ card.type.helpApp }}{{ card.newOnly ? ' · new elements only' : '' }}</span>
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
    </template>
  </div>
</template>

<style scoped>
.empty {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.doable-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  margin-bottom: var(--space-1);
  cursor: pointer;
}

.hidden-note {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-bottom: var(--space-2);
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

.quest-card.not-doable {
  opacity: 0.75;
}

.needs {
  font-style: italic;
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

.scoring-bonus.held {
  color: var(--color-success);
  font-weight: var(--font-weight-semibold);
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
