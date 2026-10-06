<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { api, type SubmissionData, type EventData, type QuestProgressData } from '../api'
import { PLATFORMS, platformInfo } from '../composables/useQuestTypes'

const route = useRoute()
const eventId = route.params.id as string

const event = ref<EventData | null>(null)
const submissions = ref<SubmissionData[]>([])
const loading = ref(false)
const harvesting = ref(false)
const error = ref<string | null>(null)
const notification = ref<string | null>(null)

// Filter state
const filterStatus = ref<'all' | 'pending' | 'verified'>('all')
const filterPlatform = ref<string>('all')

/** Platform filter options: every known platform, in the shared display order. */
const platformOptions = Object.entries(PLATFORMS).map(([value, { label }]) => ({ value, label }))

// Team progress drawer, opened from a submission's team cell
const progressTeam = ref<{ id: number; name: string } | null>(null)
const teamProgress = ref<QuestProgressData[]>([])
const progressLoading = ref(false)

const loadSubmissions = async () => {
  try {
    loading.value = true
    event.value = await api.getEvent(eventId)
    submissions.value = await api.getSubmissions(eventId)
  } catch (err: any) {
    error.value = 'Failed to load submissions for this event.'
  } finally {
    loading.value = false
  }
}

const filteredSubmissions = computed(() => {
  return submissions.value.filter((s) => {
    if (filterStatus.value === 'pending' && s.is_verified) return false
    if (filterStatus.value === 'verified' && !s.is_verified) return false
    if (filterPlatform.value !== 'all' && s.platform !== filterPlatform.value) return false
    return true
  })
})

const handleVerifyToggle = async (submission: SubmissionData) => {
  const newVerifiedState = !submission.is_verified
  try {
    const updated = await api.verifySubmission(submission.id, 'Host')
    submission.is_verified = updated.is_verified
    submission.verified_by_username = updated.verified_by_username
    submission.verified_at = updated.verified_at

    // Verification changes progress counts and points; keep an open progress drawer current
    if (progressTeam.value && submission.team === progressTeam.value.id) {
      showTeamProgress(progressTeam.value.id, progressTeam.value.name)
    }

    notification.value = updated.is_verified
      ? `Submission #${submission.external_id} marked as verified!`
      : `Submission #${submission.external_id} marked as pending.`

    setTimeout(() => {
      notification.value = null
    }, 3000)
  } catch (err: any) {
    error.value = 'Failed to update verification status.'
  }
}

const handleTriggerHarvest = async () => {
  try {
    harvesting.value = true
    const res = await fetch('/api/submissions/trigger_harvest/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event: eventId })
    })
    if (res.ok) {
      notification.value = 'Harvesting cycle complete! Staged new submissions.'
      await loadSubmissions()
    } else {
      error.value = 'Harvest cycle encountered an issue.'
    }
  } catch (err) {
    error.value = 'Could not trigger harvest.'
  } finally {
    harvesting.value = false
  }
}

/** Badge text for a submission's platform, e.g. "🕰️ OpenHistoricalMap". */
const getPlatformBadge = (sub: SubmissionData) => {
  const info = platformInfo(sub.platform, sub.platform_display)
  return `${info.icon} ${info.label}`
}

const getPlatformColor = (sub: SubmissionData) => platformInfo(sub.platform).color

/** "3 elements" for counted quests; element_count defaults to 1 on older submissions. */
const formatElementCount = (count?: number) => {
  const n = count ?? 1
  return `${n} element${n === 1 ? '' : 's'}`
}

const formatDateTime = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''

/** Opens the progress drawer for a team (reloads it so it reflects the latest verifications). */
const showTeamProgress = async (teamId: number, teamName: string) => {
  progressTeam.value = { id: teamId, name: teamName }
  progressLoading.value = true
  try {
    teamProgress.value = await api.getTeamProgress(teamId)
  } catch {
    teamProgress.value = []
    error.value = `Failed to load progress for ${teamName}.`
  } finally {
    progressLoading.value = false
  }
}

onMounted(() => {
  loadSubmissions()
})
</script>

<template>
  <div class="host-verification-view">
    <header class="verification-header">
      <div class="header-left">
        <h2 class="page-title">Host Verification Portal</h2>
        <p v-if="event" class="page-subtitle">{{ event.title }} (#{{ event.hashtag }})</p>
      </div>

      <div class="header-actions">
        <button
          class="btn btn-secondary"
          :disabled="harvesting"
          @click="handleTriggerHarvest"
        >
          {{ harvesting ? 'Harvesting...' : '🔄 Poll External APIs Now' }}
        </button>
      </div>
    </header>

    <div v-if="notification" class="alert alert-success">{{ notification }}</div>
    <div v-if="error" class="alert alert-danger">{{ error }}</div>

    <!-- Filter Bar -->
    <div class="card filter-bar">
      <div class="filter-group">
        <label class="filter-label">Verification Status:</label>
        <select v-model="filterStatus" class="form-select filter-select">
          <option value="all">All Submissions</option>
          <option value="pending">Pending Only</option>
          <option value="verified">Verified Only</option>
        </select>
      </div>

      <div class="filter-group">
        <label class="filter-label">Source Platform:</label>
        <select v-model="filterPlatform" class="form-select filter-select">
          <option value="all">All Platforms</option>
          <option v-for="option in platformOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </div>

      <div class="filter-stats">
        <span>Showing <strong>{{ filteredSubmissions.length }}</strong> of {{ submissions.length }}</span>
      </div>
    </div>

    <!-- Team progress drawer -->
    <div v-if="progressTeam" class="card progress-card">
      <div class="progress-header">
        <h3 class="progress-title">Progress: {{ progressTeam.name }}</h3>
        <button type="button" class="btn btn-outline" @click="progressTeam = null">Close</button>
      </div>
      <p v-if="progressLoading" class="text-muted">Loading progress…</p>
      <ul v-else class="progress-list">
        <li v-for="row in teamProgress" :key="row.quest" :class="['progress-row', { done: row.completed_at }]">
          <span class="progress-quest">{{ row.quest_title }}</span>
          <span class="progress-count">{{ row.count }}/{{ row.target_count }}</span>
          <span class="progress-points">
            {{ row.points_awarded ? `+${row.points_reward} pts` : `${row.points_reward} pts` }}
          </span>
        </li>
        <li v-if="teamProgress.length === 0" class="text-muted">No quests for this event.</li>
      </ul>
    </div>

    <!-- Submissions Table -->
    <div class="card table-card">
      <div v-if="loading" class="status-box">Loading harvested submissions...</div>
      <div v-else-if="filteredSubmissions.length === 0" class="empty-state">
        <p>No submissions found matching criteria.</p>
      </div>

      <table v-else class="submissions-table">
        <thead>
          <tr>
            <th style="width: 140px;">Platform</th>
            <th>ID / Changeset</th>
            <th>Elements</th>
            <th>Contributor</th>
            <th>Matched Quest</th>
            <th>Assigned Team</th>
            <th>Diff Preview</th>
            <th style="width: 140px; text-align: center;">Verified</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="sub in filteredSubmissions" :key="sub.id" :class="{ 'row-verified': sub.is_verified }">
            <td>
              <span class="badge platform-badge" :style="{ '--platform-color': getPlatformColor(sub) }">
                {{ getPlatformBadge(sub) }}
              </span>
            </td>
            <td>
              <a :href="sub.external_url" target="_blank" class="external-link">
                #{{ sub.external_id }} ↗
              </a>
              <span v-if="sub.contributed_at" class="contributed-at">{{ formatDateTime(sub.contributed_at) }}</span>
            </td>
            <td class="element-count">{{ formatElementCount(sub.element_count) }}</td>
            <td>
              <strong>{{ sub.author_username }}</strong>
            </td>
            <td>
              <span v-if="sub.quest_title" class="badge badge-success">{{ sub.quest_title }}</span>
              <span v-else class="text-muted">Uncategorized</span>
            </td>
            <td>
              <template v-if="sub.team_name && sub.team">
                <span class="team-badge">{{ sub.team_name }}</span>
                <button type="button" class="link-btn" @click="showTeamProgress(sub.team, sub.team_name)">
                  progress
                </button>
              </template>
              <span v-else class="text-muted">Individual</span>
            </td>
            <td>
              <div class="diff-preview">
                <template v-if="sub.diff_payload && sub.diff_payload.modified_tags_list">
                  <div
                    v-for="(tags, idx) in sub.diff_payload.modified_tags_list.slice(0, 2)"
                    :key="idx"
                    class="tag-pill-container"
                  >
                    <span v-for="(v, k) in tags" :key="k" class="tag-pill">
                      <code>{{ k }}={{ v }}</code>
                    </span>
                  </div>
                </template>
                <template v-else-if="sub.diff_payload && sub.diff_payload.title">
                  <span class="media-preview">{{ sub.diff_payload.title }}</span>
                </template>
                <template v-else>
                  <code class="diff-json">{{ JSON.stringify(sub.diff_payload).substring(0, 60) }}...</code>
                </template>
              </div>
            </td>
            <td style="text-align: center;">
              <button
                :class="['btn', sub.is_verified ? 'btn-primary' : 'btn-outline']"
                @click="handleVerifyToggle(sub)"
              >
                {{ sub.is_verified ? '✓ Verified' : 'Verify' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.host-verification-view {
  max-width: var(--max-content-width);
  margin: 0 auto;
  padding: var(--space-8) var(--space-4);
  width: 100%;
}

.verification-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-6);
  flex-wrap: wrap;
  gap: var(--space-4);
}

.page-title {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
}

.page-subtitle {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.filter-bar {
  display: flex;
  gap: var(--space-6);
  align-items: center;
  margin-bottom: var(--space-6);
  padding: var(--space-4);
  flex-wrap: wrap;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.filter-label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.filter-select {
  padding: var(--space-1) var(--space-3);
  font-size: var(--font-size-sm);
  width: auto;
}

.filter-stats {
  margin-left: auto;
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.table-card {
  overflow-x: auto;
  padding: var(--space-4);
}

.submissions-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.submissions-table th {
  text-align: left;
  padding: var(--space-3);
  border-bottom: 2px solid var(--color-border);
  color: var(--color-text-muted);
  font-weight: var(--font-weight-semibold);
}

.submissions-table td {
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-border);
  vertical-align: middle;
}

.row-verified {
  background-color: var(--color-success-light);
}

.external-link {
  font-weight: var(--font-weight-medium);
  font-family: var(--font-family-mono);
}

.platform-badge {
  /* Tinted with the platform's quest-type colour */
  color: var(--platform-color, var(--color-primary));
  border: 1px solid var(--platform-color, var(--color-primary-border));
  background-color: var(--color-bg-surface);
  white-space: nowrap;
}

.contributed-at {
  display: block;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.element-count {
  white-space: nowrap;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.link-btn {
  display: block;
  background: none;
  border: none;
  padding: 0;
  margin-top: 2px;
  color: var(--color-primary);
  font-size: var(--font-size-xs);
  cursor: pointer;
}

.link-btn:hover {
  text-decoration: underline;
}

.progress-card {
  margin-bottom: var(--space-6);
  padding: var(--space-4);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
}

.progress-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
}

.progress-list {
  list-style: none;
}

.progress-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: var(--space-4);
  padding: var(--space-1) 0;
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-sm);
}

.progress-row.done {
  color: var(--color-success);
}

.progress-count, .progress-points {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.team-badge {
  background-color: var(--color-bg-subtle);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-medium);
}

.diff-preview {
  max-width: 300px;
}

.tag-pill-container {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin-bottom: var(--space-1);
}

.tag-pill {
  background-color: var(--color-bg-subtle);
  border: 1px solid var(--color-border-strong);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
}

.diff-json {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.text-muted {
  color: var(--color-text-muted);
  font-style: italic;
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

.empty-state, .status-box {
  text-align: center;
  padding: var(--space-8);
  color: var(--color-text-muted);
}
</style>
