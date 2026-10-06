<script setup lang="ts">
/**
 * Manage-event layout: the event's header (title, hashtag, dates, active toggle) and tabs for
 * Overview, Quests (builder), Verification and Teams. The tab content is the child route.
 */
import { ref, computed, watch } from 'vue'
import { useRoute, RouterLink, RouterView } from 'vue-router'
import { api, type EventData } from '../../api'
import { eventStatus, formatEventRange, EVENT_STATUS_LABELS } from '../../composables/eventForm'

const route = useRoute()
const eventId = computed(() => String(route.params.id))

const event = ref<EventData | null>(null)
const error = ref<string | null>(null)
const toggling = ref(false)

const load = async () => {
  error.value = null
  try {
    event.value = await api.getEvent(eventId.value)
  } catch {
    event.value = null
    error.value = `Could not load event ${eventId.value}.`
  }
}

/** PATCHes is_active; the switch flips back if the server refuses. */
const toggleActive = async () => {
  if (!event.value) return
  const next = !event.value.is_active
  toggling.value = true
  error.value = null
  try {
    event.value = await api.updateEvent(event.value.id, { is_active: next })
  } catch (err: any) {
    error.value = err?.message || 'Could not change whether the event is active.'
  } finally {
    toggling.value = false
  }
}

const status = computed(() => (event.value ? EVENT_STATUS_LABELS[eventStatus(event.value)] : null))

const tabs = computed(() => [
  { to: `/backoffice/events/${eventId.value}`, label: 'Overview', exact: true },
  { to: `/backoffice/events/${eventId.value}/quests`, label: 'Quests', exact: false },
  { to: `/backoffice/events/${eventId.value}/verify`, label: 'Verification', exact: false },
  { to: `/backoffice/events/${eventId.value}/teams`, label: 'Teams', exact: false }
])

const isActiveTab = (tab: { to: string; exact: boolean }) =>
  tab.exact ? route.path.replace(/\/$/, '') === tab.to : route.path.startsWith(tab.to)

// Reload when moving between events without leaving the layout
watch(eventId, load, { immediate: true })
</script>

<template>
  <div class="manage-event">
    <header class="manage-header">
      <div class="manage-inner">
        <p class="breadcrumb"><RouterLink to="/backoffice">Events</RouterLink> /</p>
        <div v-if="event" class="title-row">
          <h1 class="event-title">{{ event.title }}</h1>
          <span class="badge badge-primary">#{{ event.hashtag }}</span>
          <span v-if="status" :class="['badge', status.badge]">{{ status.label }}</span>
        </div>
        <h1 v-else class="event-title">Event {{ eventId }}</h1>

        <div v-if="event" class="meta-row">
          <span class="dates">{{ formatEventRange(event.start_time, event.end_time) }}</span>
          <label class="active-switch">
            <input type="checkbox" :checked="event.is_active" :disabled="toggling" @change="toggleActive" />
            Active
          </label>
          <RouterLink :to="`/backoffice/events/${eventId}/edit`" class="meta-link">Edit event</RouterLink>
          <RouterLink :to="`/events/${eventId}/map`" class="meta-link" target="_blank">Participant map ↗</RouterLink>
        </div>
        <p v-if="error" class="error-text" role="alert">{{ error }}</p>

        <nav class="tabs" aria-label="Event sections">
          <RouterLink
            v-for="tab in tabs"
            :key="tab.to"
            :to="tab.to"
            :class="['tab', { active: isActiveTab(tab) }]"
            :aria-current="isActiveTab(tab) ? 'page' : undefined"
          >
            {{ tab.label }}
          </RouterLink>
        </nav>
      </div>
    </header>

    <!-- Keyed by event so tab views reload when switching events -->
    <RouterView :key="eventId" />
  </div>
</template>

<style scoped>
.manage-event {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.manage-header {
  background-color: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border);
}

.manage-inner {
  max-width: 1400px;
  margin: 0 auto;
  padding: var(--space-4) var(--space-4) 0;
}

.breadcrumb {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.event-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}

.meta-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
  margin-top: var(--space-1);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.active-switch {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--color-text-main);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
}

.meta-link {
  font-size: var(--font-size-sm);
}

.error-text {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  margin-top: var(--space-1);
}

.tabs {
  display: flex;
  gap: var(--space-1);
  margin-top: var(--space-3);
  overflow-x: auto;
}

.tab {
  padding: var(--space-2) var(--space-3);
  border-bottom: 3px solid transparent;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  white-space: nowrap;
}

.tab:hover {
  color: var(--color-text-main);
  text-decoration: none;
}

.tab.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}
</style>
