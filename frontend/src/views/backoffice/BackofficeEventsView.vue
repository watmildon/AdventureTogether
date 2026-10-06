<script setup lang="ts">
/**
 * Back office home: every event, active or not, with its status, dates, hashtag and quest /
 * team counts, plus "New event" and a per-event "Manage" link.
 */
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { api, type EventData } from '../../api'
import { eventStatus, formatEventRange, EVENT_STATUS_LABELS } from '../../composables/eventForm'

const events = ref<EventData[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

/** Quest and team totals per event id, filled in after the list (one cheap count call each). */
const counts = ref<Record<number, { quests?: number; teams?: number }>>({})

const loadCounts = () =>
  Promise.all(
    events.value.map(async (event) => {
      const [quests, teams] = await Promise.allSettled([api.countQuests(event.id), api.countTeams(event.id)])
      counts.value = {
        ...counts.value,
        [event.id]: {
          quests: quests.status === 'fulfilled' ? quests.value : undefined,
          teams: teams.status === 'fulfilled' ? teams.value : undefined
        }
      }
    })
  )

const load = async () => {
  loading.value = true
  error.value = null
  try {
    // Newest first, so a freshly created event is at the top
    events.value = (await api.getEvents()).sort((a, b) => b.start_time.localeCompare(a.start_time) || b.id - a.id)
    loadCounts()
  } catch {
    error.value = 'Failed to load events.'
  } finally {
    loading.value = false
  }
}

/** "1 team", "4 teams", or "– teams" while unknown. */
const countText = (n: number | undefined, noun: string) => `${n ?? '–'} ${noun}${n === 1 ? '' : 's'}`

const statusOf = (event: EventData) => EVENT_STATUS_LABELS[eventStatus(event)]

onMounted(load)
</script>

<template>
  <div class="backoffice-events">
    <header class="page-header">
      <div>
        <h1 class="page-title">Events</h1>
        <p class="page-subtitle">All events, including inactive ones. Participants only see active events that have not ended.</p>
      </div>
      <RouterLink to="/backoffice/events/new" class="btn btn-primary">+ New event</RouterLink>
    </header>

    <div v-if="loading" class="status-msg">Loading events...</div>
    <div v-else-if="error" class="status-msg error-msg">{{ error }}</div>
    <div v-else-if="events.length === 0" class="card status-msg">No events yet. Create the first one.</div>

    <ul v-else class="event-list">
      <li v-for="event in events" :key="event.id" class="card event-row" :data-event-id="event.id">
        <div class="event-main">
          <div class="event-title-line">
            <span :class="['badge', statusOf(event).badge]">{{ statusOf(event).label }}</span>
            <h2 class="event-title">{{ event.title }}</h2>
          </div>
          <p class="event-meta">
            <span class="hashtag">#{{ event.hashtag }}</span>
            <span>{{ formatEventRange(event.start_time, event.end_time) }}</span>
          </p>
          <p class="event-counts">
            <span>{{ countText(counts[event.id]?.quests, 'quest') }}</span>
            <span>{{ countText(counts[event.id]?.teams, 'team') }}</span>
          </p>
        </div>
        <div class="event-actions">
          <RouterLink :to="`/backoffice/events/${event.id}`" class="btn btn-primary">Manage</RouterLink>
          <RouterLink :to="`/backoffice/events/${event.id}/edit`" class="btn btn-outline">Edit</RouterLink>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.backoffice-events {
  max-width: 1400px;
  margin: 0 auto;
  padding: var(--space-8) var(--space-4);
  width: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.page-title {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
}

.page-subtitle {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.event-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.event-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-4);
}

.event-main {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.event-title-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.event-title {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
}

.event-meta,
.event-counts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-4);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.hashtag {
  font-family: var(--font-family-mono);
  color: var(--color-text-main);
}

.event-counts {
  font-size: var(--font-size-xs);
}

.event-actions {
  display: flex;
  gap: var(--space-2);
}

.status-msg {
  text-align: center;
  padding: var(--space-6);
  color: var(--color-text-muted);
}

.error-msg {
  color: var(--color-danger);
}
</style>
