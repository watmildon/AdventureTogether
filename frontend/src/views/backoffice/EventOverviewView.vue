<script setup lang="ts">
/**
 * Manage-event overview: leaderboard, submissions waiting for verification, a manual harvest
 * ("Poll external APIs now") with per-platform results, and the links to give participants.
 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { api, type LeaderboardEntry, type HarvestResult } from '../../api'
import LeaderboardList from '../../components/LeaderboardList.vue'
import { platformInfo } from '../../composables/useQuestTypes'
import { harvestPlatformRows, HARVEST_STAT_KEYS } from '../../composables/eventForm'

const route = useRoute()
const eventId = route.params.id as string

const leaderboard = ref<LeaderboardEntry[]>([])
const leaderboardError = ref<string | null>(null)
const pendingCount = ref<number | null>(null)
const questCount = ref<number | null>(null)

const harvesting = ref(false)
const harvest = ref<HarvestResult | null>(null)
const harvestError = ref<string | null>(null)
const harvestRows = computed(() => harvestPlatformRows(harvest.value?.stats))
const harvestWarnings = computed<string[]>(() => (Array.isArray(harvest.value?.stats?.warnings) ? harvest.value!.stats.warnings : []))

/** Absolute participant URLs so a host can copy them into an invite. */
const mapUrl = computed(() => `${window.location.origin}/events/${eventId}/map`)
const joinUrl = computed(() => `${window.location.origin}/events/${eventId}/join`)

const loadLeaderboard = async () => {
  try {
    leaderboard.value = await api.getLeaderboard(eventId)
    leaderboardError.value = null
  } catch {
    leaderboardError.value = 'Leaderboard unavailable.'
  }
}

const loadCounts = async () => {
  const [pending, quests] = await Promise.allSettled([api.countSubmissions(eventId, false), api.countQuests(eventId)])
  pendingCount.value = pending.status === 'fulfilled' ? pending.value : null
  questCount.value = quests.status === 'fulfilled' ? quests.value : null
}

/** Runs the harvesters now; new submissions and scores show straight after. */
const pollNow = async () => {
  harvesting.value = true
  harvestError.value = null
  try {
    harvest.value = await api.triggerHarvest(eventId)
    await Promise.all([loadCounts(), loadLeaderboard()])
  } catch (err: any) {
    harvest.value = null
    harvestError.value = err?.message || 'The harvest failed.'
  } finally {
    harvesting.value = false
  }
}

onMounted(() => {
  loadLeaderboard()
  loadCounts()
})
</script>

<template>
  <div class="overview">
    <section class="card stat-card">
      <h2 class="card-title">Waiting for verification</h2>
      <p class="big-number" data-testid="pending-count">{{ pendingCount ?? '–' }}</p>
      <p class="card-desc">
        Harvested submissions not verified yet.
        <RouterLink :to="`/backoffice/events/${eventId}/verify`">Review them</RouterLink>
      </p>
      <p class="card-desc">
        {{ questCount ?? '–' }} quests. <RouterLink :to="`/backoffice/events/${eventId}/quests`">Edit quests</RouterLink>
      </p>
    </section>

    <section class="card leaderboard-card">
      <h2 class="card-title">Leaderboard</h2>
      <p v-if="leaderboardError" class="card-desc">{{ leaderboardError }}</p>
      <p v-else-if="leaderboard.length === 0" class="card-desc">
        No teams yet. <RouterLink :to="`/backoffice/events/${eventId}/teams`">Create one</RouterLink>
      </p>
      <LeaderboardList v-else :entries="leaderboard" :limit="50" />
    </section>

    <section class="card harvest-card">
      <div class="harvest-head">
        <div>
          <h2 class="card-title">Harvest</h2>
          <p class="card-desc">Contributions are fetched on a schedule. Poll now to pick up recent edits straight away.</p>
        </div>
        <button type="button" class="btn btn-secondary" :disabled="harvesting" @click="pollNow">
          {{ harvesting ? 'Polling...' : '🔄 Poll external APIs now' }}
        </button>
      </div>

      <p v-if="harvestError" class="error-text" role="alert">{{ harvestError }}</p>
      <template v-if="harvest">
        <p class="card-desc">{{ harvest.message }}</p>
        <p v-if="harvestRows.length === 0" class="card-desc">No platform needed polling (no active quests with harvested types).</p>
        <div v-else class="table-wrap">
          <table class="harvest-table">
            <thead>
              <tr>
                <th>Platform</th>
                <th v-for="key in HARVEST_STAT_KEYS" :key="key">{{ key }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in harvestRows" :key="row.platform" :data-platform="row.platform">
                <td>{{ platformInfo(row.platform).icon }} {{ platformInfo(row.platform).label }}</td>
                <td v-for="key in HARVEST_STAT_KEYS" :key="key" :class="{ bad: key === 'errors' && row.counts.errors > 0 }">{{ row.counts[key] }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <ul v-if="harvestWarnings.length" class="warnings">
          <li v-for="warning in harvestWarnings" :key="warning">⚠️ {{ warning }}</li>
        </ul>
      </template>
    </section>

    <section class="card links-card">
      <h2 class="card-title">For participants</h2>
      <p class="card-desc">Share these links (or a QR code of them) with participants.</p>
      <dl class="links">
        <dt>Map</dt>
        <dd><a :href="mapUrl" target="_blank" rel="noopener">{{ mapUrl }}</a></dd>
        <dt>Join a team</dt>
        <dd><a :href="joinUrl" target="_blank" rel="noopener">{{ joinUrl }}</a></dd>
      </dl>
    </section>
  </div>
</template>

<style scoped>
.overview {
  max-width: 1400px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-4) var(--space-10);
  width: 100%;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
  align-items: start;
}

.harvest-card,
.links-card {
  grid-column: span 2;
}

.card-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  margin-bottom: var(--space-1);
}

.card-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin-bottom: var(--space-2);
}

.big-number {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  font-variant-numeric: tabular-nums;
}

.links {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-1) var(--space-3);
  font-size: var(--font-size-sm);
}

.links dt {
  color: var(--color-text-muted);
}

.links dd {
  overflow-wrap: anywhere;
}

.harvest-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.table-wrap {
  overflow-x: auto;
}

.harvest-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.harvest-table th,
.harvest-table td {
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--color-border);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.harvest-table th:first-child,
.harvest-table td:first-child {
  text-align: left;
}

.harvest-table th {
  font-size: var(--font-size-xs);
  text-transform: capitalize;
  color: var(--color-text-muted);
}

.bad {
  color: var(--color-danger);
  font-weight: var(--font-weight-semibold);
}

.warnings {
  list-style: none;
  margin-top: var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--color-warning);
}

.error-text {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
}

@media (max-width: 768px) {
  .overview {
    grid-template-columns: 1fr;
    padding: var(--space-4) var(--space-3);
  }

  .harvest-card,
  .links-card {
    grid-column: auto;
  }
}
</style>
