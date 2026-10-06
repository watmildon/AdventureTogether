<script setup lang="ts">
/**
 * Manage-event Teams tab: every team with its join code, size, score and members (with the
 * contributor usernames the harvesters match on), plus a form to create a team, e.g. one per
 * table at a workshop, whose code the host hands out.
 */
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api, type TeamData, type TeamMembershipData } from '../../api'

const route = useRoute()
const eventId = route.params.id as string

const teams = ref<TeamData[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

const newTeamName = ref('')
const creating = ref(false)
const createError = ref<string | null>(null)
const created = ref<TeamData | null>(null)

/** Highest score first, then name, like the leaderboard. */
const sortedTeams = computed(() => [...teams.value].sort((a, b) => b.score - a.score || a.name.localeCompare(b.name)))

const load = async () => {
  loading.value = true
  error.value = null
  try {
    teams.value = await api.getTeams(eventId)
  } catch {
    error.value = 'Failed to load teams.'
  } finally {
    loading.value = false
  }
}

const createTeam = async () => {
  const name = newTeamName.value.trim()
  if (!name) {
    createError.value = 'Give the team a name.'
    return
  }
  creating.value = true
  createError.value = null
  try {
    created.value = await api.createTeam(eventId, name)
    newTeamName.value = ''
    await load()
  } catch (err: any) {
    createError.value = err?.message || 'Could not create the team.'
  } finally {
    creating.value = false
  }
}

/** "osm: alice · wikimedia: Alice · github: alice-gh", skipping blanks. */
const usernamesText = (member: TeamMembershipData) =>
  [
    member.osm_username && `OSM: ${member.osm_username}`,
    member.wikimedia_username && `Wikimedia: ${member.wikimedia_username}`,
    member.github_username && `GitHub: ${member.github_username}`
  ]
    .filter(Boolean)
    .join(' · ')

onMounted(load)
</script>

<template>
  <div class="teams-view">
    <section class="card create-card">
      <h2 class="card-title">Create team</h2>
      <form class="create-form" @submit.prevent="createTeam">
        <label class="sr-only" for="newTeamName">Team name</label>
        <input id="newTeamName" v-model="newTeamName" type="text" class="form-input" placeholder="e.g. Table 4 Mappers" />
        <button type="submit" class="btn btn-primary" :disabled="creating">{{ creating ? 'Creating...' : 'Create team' }}</button>
      </form>
      <p v-if="createError" class="error-text" role="alert">{{ createError }}</p>
      <p v-if="created" class="created-note" role="status">
        Created <strong>{{ created.name }}</strong>. Join code <code>{{ created.join_code }}</code>
      </p>
    </section>

    <div v-if="loading" class="status-msg">Loading teams...</div>
    <div v-else-if="error" class="status-msg error-text">{{ error }}</div>
    <div v-else-if="teams.length === 0" class="card status-msg">No teams yet.</div>

    <div v-else class="card table-card">
      <table class="teams-table">
        <thead>
          <tr>
            <th>Team</th>
            <th>Join code</th>
            <th class="num">Members</th>
            <th class="num">Score</th>
            <th>Members and usernames</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="team in sortedTeams" :key="team.id" :data-team-id="team.id">
            <td class="team-name" data-label="Team">{{ team.name }}</td>
            <td data-label="Join code"><code class="code">{{ team.join_code }}</code></td>
            <td class="num" data-label="Members">{{ team.member_count }}</td>
            <td class="num" data-label="Score">{{ team.score }}</td>
            <td data-label="People">
              <span v-if="team.memberships.length === 0" class="muted">Nobody yet</span>
              <ul v-else class="members">
                <li v-for="member in team.memberships" :key="member.id">
                  <strong>{{ member.display_name || member.user_identifier }}</strong>
                  <span v-if="usernamesText(member)" class="usernames">{{ usernamesText(member) }}</span>
                  <span v-else class="muted usernames">no usernames given</span>
                </li>
              </ul>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.teams-view {
  max-width: 1400px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-4) var(--space-10);
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.card-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  margin-bottom: var(--space-2);
}

.create-form {
  display: flex;
  gap: var(--space-2);
  max-width: 520px;
}

.create-form .btn {
  white-space: nowrap;
}

.created-note {
  margin-top: var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--color-success);
}

.code,
.created-note code {
  font-family: var(--font-family-mono);
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.05em;
}

.table-card {
  padding: 0;
  overflow-x: auto;
}

.teams-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.teams-table th,
.teams-table td {
  text-align: left;
  vertical-align: top;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.teams-table th {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  background-color: var(--color-bg-subtle);
}

.teams-table .num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.team-name {
  font-weight: var(--font-weight-semibold);
}

.members {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.usernames {
  display: block;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.muted {
  color: var(--color-text-subtle);
}

.error-text {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  margin-top: var(--space-2);
}

.status-msg {
  text-align: center;
  padding: var(--space-6);
  color: var(--color-text-muted);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

/* Phone width: each team becomes a stacked block instead of a wide table */
@media (max-width: 640px) {
  .teams-view {
    padding: var(--space-4) var(--space-3);
  }

  .teams-table thead {
    display: none;
  }

  .teams-table tr {
    display: block;
    border-bottom: 1px solid var(--color-border);
    padding: var(--space-2) 0;
  }

  .teams-table td {
    display: flex;
    justify-content: space-between;
    gap: var(--space-3);
    border: none;
    padding: var(--space-1) var(--space-3);
    text-align: right;
  }

  .teams-table td::before {
    content: attr(data-label);
    color: var(--color-text-muted);
    font-size: var(--font-size-xs);
    text-align: left;
  }

  .members {
    align-items: flex-end;
  }
}
</style>
