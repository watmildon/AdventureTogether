<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { api, type TeamData, type PlatformUsernames } from '../api'
import { readProfile, saveIdentity, ensureParticipantId } from '../composables/participantProfile'

const route = useRoute()
const router = useRouter()
const eventId = route.params.id as string

const joinCode = ref('')
const teamName = ref('')
const activeTab = ref<'join' | 'create'>('join')

// Prefilled from the landing page profile (same localStorage keys). The usernames stay
// editable here because they are sent with the join so harvested edits credit the team.
const profile = readProfile()
const userIdentifier = ref(ensureParticipantId())
const displayName = ref(profile.displayName)
const osmUsername = ref(profile.usernames.osm_username)
const wikimediaUsername = ref(profile.usernames.wikimedia_username)
const githubUsername = ref(profile.usernames.github_username)

const existingTeams = ref<TeamData[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const successMsg = ref<string | null>(null)

/** Saves the participant's name and usernames back to the profile and returns the usernames for the join call. */
const persistParticipant = (): PlatformUsernames =>
  saveIdentity(displayName.value, {
    osm_username: osmUsername.value,
    wikimedia_username: wikimediaUsername.value,
    github_username: githubUsername.value
  })

/**
 * Remembers the joined team. `team_for_event_<id>` is the event-scoped record the map reads
 * first; `team_id` / `team_name` are the simple global keys kept for other consumers.
 */
const persistTeam = (team: TeamData) => {
  localStorage.setItem(`team_for_event_${eventId}`, JSON.stringify(team))
  localStorage.setItem('team_id', String(team.id))
  localStorage.setItem('team_name', team.name)
}

const loadTeams = async () => {
  try {
    existingTeams.value = await api.getTeams(eventId)
  } catch (err: any) {
    // Ignore initial team fetch error
  }
}

const handleJoin = async () => {
  if (!joinCode.value.trim()) {
    error.value = 'Please enter a valid join code.'
    return
  }
  if (!displayName.value.trim()) {
    error.value = 'Please enter your display name.'
    return
  }

  try {
    loading.value = true
    error.value = null
    const usernames = persistParticipant()

    const result = await api.joinTeam(joinCode.value, userIdentifier.value, displayName.value, usernames)
    successMsg.value = result.message
    persistTeam(result.team)

    setTimeout(() => {
      router.push(`/events/${eventId}/map`)
    }, 1200)
  } catch (err: any) {
    error.value = err.message || 'Failed to join team.'
  } finally {
    loading.value = false
  }
}

const handleCreate = async () => {
  if (!teamName.value.trim()) {
    error.value = 'Please enter a team name.'
    return
  }
  if (!displayName.value.trim()) {
    error.value = 'Please enter your display name.'
    return
  }

  try {
    loading.value = true
    error.value = null
    const usernames = persistParticipant()

    const newTeam = await api.createTeam(eventId, teamName.value)
    const result = await api.joinTeam(newTeam.join_code, userIdentifier.value, displayName.value, usernames)
    successMsg.value = `Team "${newTeam.name}" created! Join Code: ${newTeam.join_code}`
    persistTeam(result.team)

    setTimeout(() => {
      router.push(`/events/${eventId}/map`)
    }, 1500)
  } catch (err: any) {
    error.value = err.message || 'Failed to create team.'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadTeams()
})
</script>

<template>
  <div class="join-team-view">
    <div class="card form-card">
      <h2 class="form-title">Team Management</h2>
      <p class="form-subtitle">Event #{{ eventId }}</p>

      <p class="profile-note">
        Filled in from <RouterLink to="/">your profile</RouterLink>. Changes here are saved to it too.
      </p>

      <div v-if="successMsg" class="alert alert-success">{{ successMsg }}</div>
      <div v-if="error" class="alert alert-danger">{{ error }}</div>

      <div class="form-group">
        <label class="form-label" for="displayName">Your Display Name</label>
        <input
          id="displayName"
          v-model="displayName"
          type="text"
          class="form-input"
          placeholder="e.g. Alex Cartographer"
        />
      </div>

      <fieldset class="usernames">
        <legend class="form-label">Your contributor usernames <span class="optional">(optional)</span></legend>
        <p class="usernames-hint">So your edits are credited to your team.</p>
        <div class="form-group">
          <label class="form-label" for="osmUsername">OpenStreetMap username</label>
          <input id="osmUsername" v-model="osmUsername" type="text" class="form-input" placeholder="also used for OpenHistoricalMap" autocomplete="off" autocapitalize="off" />
        </div>
        <div class="form-group">
          <label class="form-label" for="wikimediaUsername">Wikimedia username</label>
          <input id="wikimediaUsername" v-model="wikimediaUsername" type="text" class="form-input" placeholder="Commons and Wikidata" autocomplete="off" autocapitalize="off" />
        </div>
        <div class="form-group">
          <label class="form-label" for="githubUsername">GitHub username</label>
          <input id="githubUsername" v-model="githubUsername" type="text" class="form-input" placeholder="for code contribution quests" autocomplete="off" autocapitalize="off" />
        </div>
      </fieldset>

      <div class="tab-controls">
        <button
          :class="['btn', activeTab === 'join' ? 'btn-primary' : 'btn-outline']"
          @click="activeTab = 'join'"
        >
          Join Existing Team
        </button>
        <button
          :class="['btn', activeTab === 'create' ? 'btn-primary' : 'btn-outline']"
          @click="activeTab = 'create'"
        >
          Create New Team
        </button>
      </div>

      <div v-if="activeTab === 'join'" class="tab-content">
        <div class="form-group">
          <label class="form-label" for="joinCode">Team Join Code</label>
          <input
            id="joinCode"
            v-model="joinCode"
            type="text"
            class="form-input"
            placeholder="e.g. ABC123"
            style="text-transform: uppercase;"
          />
        </div>
        <button class="btn btn-primary btn-block" :disabled="loading" @click="handleJoin">
          {{ loading ? 'Joining...' : 'Join Team' }}
        </button>
      </div>

      <div v-else class="tab-content">
        <div class="form-group">
          <label class="form-label" for="teamName">New Team Name</label>
          <input
            id="teamName"
            v-model="teamName"
            type="text"
            class="form-input"
            placeholder="e.g. Urban Cartographers"
          />
        </div>
        <button class="btn btn-secondary btn-block" :disabled="loading" @click="handleCreate">
          {{ loading ? 'Creating...' : 'Create Team' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.join-team-view {
  max-width: 500px;
  margin: var(--space-8) auto;
  padding: 0 var(--space-4);
  width: 100%;
}

.form-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  text-align: center;
  margin-bottom: var(--space-1);
}

.form-subtitle {
  text-align: center;
  color: var(--color-text-muted);
  margin-bottom: var(--space-4);
}

.profile-note {
  text-align: center;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-bottom: var(--space-4);
}

.alert {
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
  font-size: var(--font-size-sm);
}

.alert-success {
  background-color: var(--color-success-light);
  color: var(--color-success);
  border: 1px solid var(--color-success-border);
}

.alert-danger {
  background-color: var(--color-danger-light);
  color: var(--color-danger);
  border: 1px solid var(--color-danger-border);
}

.usernames {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4) 0;
  margin-bottom: var(--space-6);
}

.usernames legend {
  padding: 0 var(--space-1);
  margin-bottom: 0;
}

.optional {
  color: var(--color-text-muted);
  font-weight: var(--font-weight-normal);
}

.usernames-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-bottom: var(--space-3);
}

.tab-controls {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-6);
}

.tab-controls .btn {
  flex: 1;
}

.tab-content {
  display: flex;
  flex-direction: column;
}

.btn-block {
  width: 100%;
}
</style>
