<script setup lang="ts">
/**
 * Participant landing page: who you are (profile), what you can use (tools), and the events
 * you can play with the team you joined for each. Hosts use the separate back office.
 */
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { api, type EventData, type LeaderboardEntry } from '../api'
import LeaderboardList from '../components/LeaderboardList.vue'
import ProfileEditor from '../components/ProfileEditor.vue'
import ToolsChecklist from '../components/ToolsChecklist.vue'
import { readStoredTeam } from '../composables/useQuestProgress'
import { eventStatus, formatEventRange, EVENT_STATUS_LABELS } from '../composables/eventForm'

const events = ref<EventData[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

// Top teams per event id, filled in after the event list loads (optional decoration)
const leaderboards = ref<Record<number, LeaderboardEntry[]>>({})

/** The team this device joined for each event (JoinTeamView's event-scoped record), read once per load. */
const teams = ref<Record<number, ReturnType<typeof readStoredTeam>>>({})

/** Loads each event's leaderboard in parallel; failures just leave that card without one. */
const fetchLeaderboards = async () => {
  await Promise.all(
    events.value.map(async (event) => {
      try {
        const entries = await api.getLeaderboard(event.id)
        leaderboards.value = { ...leaderboards.value, [event.id]: entries }
      } catch {
        // Leaderboard is optional on the landing page
      }
    })
  )
}

const fetchEvents = async () => {
  try {
    loading.value = true
    const all = await api.getEvents()
    // Participants only see events they can still play: active, and not over yet
    events.value = all.filter((event) => ['live', 'upcoming'].includes(eventStatus(event)))
    teams.value = Object.fromEntries(events.value.map((event) => [event.id, readStoredTeam(event.id)]))
    fetchLeaderboards()
  } catch {
    error.value = 'Failed to load scavenger hunt events.'
  } finally {
    loading.value = false
  }
}

onMounted(fetchEvents)
</script>

<template>
  <div class="home-container">
    <section class="hero-section">
      <h1 class="hero-title">AdventureTogether</h1>
      <p class="hero-subtitle">
        Collaborative open data scavenger hunts. Map OpenStreetMap amenities, submit photos to Wikimedia Commons,
        and link entities in Wikidata with your team.
      </p>
    </section>

    <section class="home-section" aria-labelledby="profile-heading">
      <h2 id="profile-heading" class="section-title">Your profile</h2>
      <div class="card">
        <ProfileEditor />
      </div>
    </section>

    <section class="home-section" aria-labelledby="tools-heading">
      <h2 id="tools-heading" class="section-title">Tools I have</h2>
      <p class="section-desc">Tick what you have or can use. The map then shows only the quests you can do.</p>
      <ToolsChecklist />
    </section>

    <section class="home-section events-section" aria-labelledby="events-heading">
      <h2 id="events-heading" class="section-title">Your events and teams</h2>

      <div v-if="loading" class="status-msg">Loading events...</div>
      <div v-else-if="error" class="status-msg error-msg">{{ error }}</div>
      <div v-else-if="events.length === 0" class="card empty-card">
        <h3>No active hunts right now</h3>
        <p>Stay tuned for the next event.</p>
      </div>

      <div v-else class="events-grid">
        <div v-for="event in events" :key="event.id" class="card event-card" :data-event-id="event.id">
          <div class="event-card-header">
            <h3 class="event-card-title">{{ event.title }}</h3>
            <span class="badge badge-primary">#{{ event.hashtag }}</span>
          </div>
          <p class="event-dates">
            <span :class="['badge', EVENT_STATUS_LABELS[eventStatus(event)].badge]">{{ EVENT_STATUS_LABELS[eventStatus(event)].label }}</span>
            {{ formatEventRange(event.start_time, event.end_time) }}
          </p>
          <p class="event-description">{{ event.description }}</p>

          <div v-if="teams[event.id]" class="team-box">
            <span class="team-label">Your team</span>
            <strong class="team-name">{{ teams[event.id]?.name || `Team #${teams[event.id]?.id}` }}</strong>
            <span v-if="teams[event.id]?.joinCode" class="join-code">
              Join code <code>{{ teams[event.id]?.joinCode }}</code>
            </span>
            <RouterLink :to="`/events/${event.id}/join`" class="change-team">Change team</RouterLink>
          </div>

          <div v-if="leaderboards[event.id]?.length" class="event-leaderboard">
            <span class="leaderboard-label">Top teams</span>
            <LeaderboardList :entries="leaderboards[event.id]" :limit="3" :highlight-team-id="teams[event.id]?.id ?? null" compact />
          </div>

          <div class="event-actions">
            <RouterLink :to="`/events/${event.id}/map`" class="btn btn-primary">Open map</RouterLink>
            <RouterLink v-if="!teams[event.id]" :to="`/events/${event.id}/join`" class="btn btn-outline">
              Join or create a team
            </RouterLink>
          </div>
        </div>
      </div>
    </section>

    <footer class="home-footer">
      Organising an event? <RouterLink to="/backoffice">Back office</RouterLink>
    </footer>
  </div>
</template>

<style scoped>
.home-container {
  max-width: var(--max-content-width);
  margin: 0 auto;
  padding: var(--space-8) var(--space-4);
  width: 100%;
}

.hero-section {
  text-align: center;
  margin-bottom: var(--space-8);
}

.hero-title {
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-main);
  margin-bottom: var(--space-2);
}

.hero-subtitle {
  font-size: var(--font-size-lg);
  color: var(--color-text-muted);
  max-width: 700px;
  margin: 0 auto;
}

.home-section {
  margin-bottom: var(--space-10);
}

.section-title {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  margin-bottom: var(--space-3);
}

.section-desc {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin-bottom: var(--space-4);
}

.events-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: var(--space-6);
}

.event-card {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.event-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.event-card-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
}

.event-dates {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-bottom: var(--space-2);
}

.event-description {
  color: var(--color-text-muted);
  margin-bottom: var(--space-4);
  flex-grow: 1;
}

.team-box {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-1) var(--space-3);
  padding: var(--space-2) var(--space-3);
  margin-bottom: var(--space-4);
  border-radius: var(--radius-md);
  background-color: var(--color-success-light);
  border: 1px solid var(--color-success-border);
  font-size: var(--font-size-sm);
}

.team-label,
.leaderboard-label {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.join-code {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.join-code code {
  font-family: var(--font-family-mono);
  color: var(--color-text-main);
}

.change-team {
  margin-left: auto;
  font-size: var(--font-size-xs);
}

.event-leaderboard {
  margin-bottom: var(--space-4);
}

.leaderboard-label {
  display: block;
  margin-bottom: var(--space-1);
}

.event-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.empty-card {
  text-align: center;
  padding: var(--space-10);
  color: var(--color-text-muted);
}

.status-msg {
  text-align: center;
  padding: var(--space-6);
  color: var(--color-text-muted);
}

.error-msg {
  color: var(--color-danger);
}

.home-footer {
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-4);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  text-align: center;
}

@media (max-width: 480px) {
  .home-container {
    padding: var(--space-6) var(--space-3);
  }

  .events-grid {
    grid-template-columns: 1fr;
  }
}
</style>
