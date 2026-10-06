<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import L from 'leaflet'
import { api, ApiError, type EventData, type QuestData, type CriteriaType, type InspiredBy, type SessionData } from '../api'
import { QUEST_TYPES, CRITERIA_TYPES, questTypeFor, formatSessionLine, formatSessionTime } from '../composables/useQuestTypes'
import { defaultRuleForm, composeValidationRules, validateRuleForm, type TagRow } from '../composables/questRules'
import { createQuestLayer, questPopupHtml } from '../composables/questLayers'

const route = useRoute()
const eventId = route.params.id as string

const event = ref<EventData | null>(null)
const quests = ref<QuestData[]>([])

// Quest Form State
const questTitle = ref('')
const questDescription = ref('')
const criteriaType = ref<CriteriaType>('osm_tags')
const pointsReward = ref(10)
const selectedType = computed(() => QUEST_TYPES[criteriaType.value])

// Per-type rule inputs; composed into validation_rules on save (see questRules.ts)
const rules = ref(defaultRuleForm())

/** Types whose rules carry a target_count (everything except check-ins). */
const usesTargetCount = computed(() => criteriaType.value !== 'location_checkin')

// Optional quest window, as datetime-local strings in the host's browser time zone
const windowStart = ref('')
const windowEnd = ref('')

// Target: a pinned point, or the whole event area (null geometry)
const targetCoords = ref<{ lat: number; lng: number } | null>(null)
const wholeArea = ref(true)

const loading = ref(false)
const error = ref<string | null>(null)
const successMsg = ref<string | null>(null)

// "Inspired by" session picker state
type SessionsState = 'loading' | 'ready' | 'no-schedule' | 'error'
const sessions = ref<SessionData[]>([])
const sessionsState = ref<SessionsState>('loading')
const sessionsError = ref('')
const sessionFilter = ref('')
const chosenSession = ref<InspiredBy | null>(null)
const manualSession = ref({ title: '', url: '' })

let map: L.Map | null = null
let perimeterLayer: L.GeoJSON | null = null
let currentMarker: L.Marker | null = null
let questsLayerGroup: L.LayerGroup | null = null

const initMap = () => {
  const mapElement = document.getElementById('builder-map')
  if (!mapElement) return

  map = L.map('builder-map').setView([37.7749, -122.4194], 14)

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
  }).addTo(map)

  questsLayerGroup = L.layerGroup().addTo(map)

  // Map click handler to set quest point target
  map.on('click', (e: L.LeafletMouseEvent) => setPointTarget(e.latlng))

  // Data may already be loaded if the API answered before the map was created
  renderMapData()
}

/** Pins (or moves) the draggable target marker and switches off "whole event area". */
const setPointTarget = (latlng: L.LatLng) => {
  targetCoords.value = { lat: latlng.lat, lng: latlng.lng }
  wholeArea.value = false
  if (currentMarker) {
    currentMarker.setLatLng(latlng)
  } else if (map) {
    currentMarker = L.marker(latlng, {
      draggable: true,
      title: 'New Quest Target'
    }).addTo(map)

    currentMarker.on('dragend', () => {
      const pos = currentMarker?.getLatLng()
      if (pos) targetCoords.value = { lat: pos.lat, lng: pos.lng }
    })
  }
}

const clearPointTarget = () => {
  if (currentMarker && map) map.removeLayer(currentMarker)
  currentMarker = null
  targetCoords.value = null
}

/** The "use whole event area" toggle: ticking it drops any pinned point. */
const onWholeAreaChange = () => {
  if (wholeArea.value) clearPointTarget()
}

const loadEventData = async () => {
  try {
    event.value = await api.getEvent(eventId)
    quests.value = await api.getQuests(eventId)
    renderMapData()
  } catch (err: any) {
    error.value = 'Failed to load event boundary.'
  }
}

/** Draws the event perimeter and existing quest targets once both the map and data exist. */
const renderMapData = () => {
  if (!map) return

  if (event.value?.bounding_polygon && !perimeterLayer) {
    perimeterLayer = L.geoJSON(event.value.bounding_polygon, {
      // Clicks inside the perimeter must reach the map so hosts can pin targets
      interactive: false,
      style: {
        color: '#2563eb',
        weight: 3,
        dashArray: '6, 6',
        fillColor: '#3b82f6',
        fillOpacity: 0.1
      }
    }).addTo(map)

    map.fitBounds(perimeterLayer.getBounds(), { padding: [30, 30] })
  }

  renderExistingQuests()
}

const renderExistingQuests = () => {
  if (!map || !questsLayerGroup) return
  questsLayerGroup.clearLayers()

  quests.value.forEach((q) => {
    // Outlines stay click-through so hosts can pin new targets inside existing quest areas
    const layer = createQuestLayer(q, questPopupHtml(q), { outlinesInteractive: false })
    if (layer) questsLayerGroup?.addLayer(layer)
  })
}

/**
 * Loads talks from the event's schedule export. 400 means the event has no
 * schedule_url (manual entry only); 502 means the schedule could not be fetched.
 */
const loadSessions = async () => {
  sessionsState.value = 'loading'
  try {
    sessions.value = await api.getSessions(eventId)
    sessionsState.value = 'ready'
  } catch (err: any) {
    if (err instanceof ApiError && err.status === 400) {
      sessionsState.value = 'no-schedule'
    } else {
      sessionsState.value = 'error'
      sessionsError.value =
        err instanceof ApiError && err.status === 502
          ? 'The event schedule could not be fetched right now. Try again later or enter the session by hand.'
          : 'Could not load sessions. Enter the session by hand.'
    }
  }
}

/** Sessions matching the filter text in title or speaker names (first 30, to keep the list short). */
const filteredSessions = computed(() => {
  const needle = sessionFilter.value.trim().toLowerCase()
  const matches = needle
    ? sessions.value.filter((session) =>
        [session.title || '', ...(session.speakers || [])].some((text) => text.toLowerCase().includes(needle))
      )
    : sessions.value
  return matches.slice(0, 30)
})

/** Stores the session in the quest's inspired_by shape (the list's `type` is not part of it). */
const chooseSession = (session: SessionData) => {
  const { type: _type, ...inspired } = session
  chosenSession.value = inspired
  sessionFilter.value = ''
}

/** What will be saved as inspired_by: a picked session, a hand-entered one, or {}. */
const inspiredByPayload = computed<InspiredBy>(() => {
  if (chosenSession.value) return chosenSession.value
  const title = manualSession.value.title.trim()
  const url = manualSession.value.url.trim()
  if (!title) return {}
  return url ? { title, url } : { title }
})

const inspiredPreview = computed(() => formatSessionLine(inspiredByPayload.value))

const addTagRow = (rows: TagRow[]) => rows.push({ key: '', value: '*' })
const removeTagRow = (rows: TagRow[], index: number) => rows.splice(index, 1)

/** datetime-local value (host's local time) to ISO 8601 UTC, or null when blank. */
const toIsoOrNull = (value: string) => (value ? new Date(value).toISOString() : null)

const resetForm = () => {
  questTitle.value = ''
  questDescription.value = ''
  rules.value = defaultRuleForm()
  windowStart.value = ''
  windowEnd.value = ''
  chosenSession.value = null
  manualSession.value = { title: '', url: '' }
  clearPointTarget()
  wholeArea.value = true
}

const handleSaveQuest = async () => {
  successMsg.value = null
  if (!questTitle.value.trim()) {
    error.value = 'Quest title is required.'
    return
  }
  if (!questDescription.value.trim()) {
    error.value = 'Quest description is required.'
    return
  }
  if (!wholeArea.value && !targetCoords.value) {
    error.value = 'Click the map to pin a target, or tick "Use whole event area".'
    return
  }
  const hasPoint = Boolean(targetCoords.value)
  const rulesProblem = validateRuleForm(criteriaType.value, rules.value, hasPoint)
  if (rulesProblem) {
    error.value = rulesProblem
    return
  }
  if (windowStart.value && windowEnd.value && windowEnd.value < windowStart.value) {
    error.value = 'The quest window must end after it starts.'
    return
  }

  // Target geometry GeoJSON Point if pinned; null means the whole event area
  const targetGeometry = targetCoords.value
    ? {
        type: 'Point',
        coordinates: [targetCoords.value.lng, targetCoords.value.lat]
      }
    : null

  try {
    loading.value = true
    error.value = null

    const created = await api.createQuest({
      event: Number(eventId),
      title: questTitle.value.trim(),
      description: questDescription.value.trim(),
      criteria_type: criteriaType.value,
      validation_rules: composeValidationRules(criteriaType.value, rules.value, hasPoint),
      target_geometry: targetGeometry,
      points_reward: pointsReward.value,
      // Types the server cannot verify yet are saved hidden from participants
      is_active: !selectedType.value.comingSoon,
      inspired_by: inspiredByPayload.value,
      window_start: toIsoOrNull(windowStart.value),
      window_end: toIsoOrNull(windowEnd.value)
    })

    successMsg.value = created.is_active
      ? `Quest "${created.title}" added successfully!`
      : `Quest "${created.title}" saved as inactive (not visible to participants yet).`
    quests.value.push(created)
    renderExistingQuests()
    resetForm()
  } catch (err: any) {
    error.value = err.message || 'Failed to create quest.'
  } finally {
    loading.value = false
  }
}

const handleDeleteQuest = async (quest: QuestData) => {
  if (!window.confirm(`Delete quest "${quest.title}"? Team progress on it will be lost.`)) return
  try {
    await api.deleteQuest(quest.id)
    quests.value = quests.value.filter((q) => q.id !== quest.id)
    renderExistingQuests()
    successMsg.value = `Quest "${quest.title}" deleted.`
  } catch {
    error.value = `Failed to delete "${quest.title}".`
  }
}

onMounted(() => {
  initMap()
  loadEventData()
  loadSessions()
})

onUnmounted(() => {
  map?.remove()
})
</script>

<template>
  <div class="host-builder-view">
    <div class="builder-sidebar card">
      <h2 class="sidebar-title">Quest Builder</h2>
      <p v-if="event" class="sidebar-subtitle">{{ event.title }} (#{{ event.hashtag }})</p>

      <div v-if="successMsg" class="alert alert-success">{{ successMsg }}</div>
      <div v-if="error" class="alert alert-danger">{{ error }}</div>

      <div class="form-group">
        <label class="form-label" for="questTitle">Quest Title</label>
        <input
          id="questTitle"
          v-model="questTitle"
          type="text"
          class="form-input"
          placeholder="e.g. Map Restaurant Opening Hours"
        />
      </div>

      <div class="form-group">
        <label class="form-label" for="questDesc">Description & Instructions</label>
        <textarea
          id="questDesc"
          v-model="questDescription"
          rows="2"
          class="form-textarea"
          placeholder="e.g. Verify and add opening hours to restaurants."
        ></textarea>
      </div>

      <div class="form-group">
        <label class="form-label" for="criteriaType">Quest Type</label>
        <select id="criteriaType" v-model="criteriaType" class="form-select">
          <option v-for="type in CRITERIA_TYPES" :key="type" :value="type">
            {{ QUEST_TYPES[type].icon }} {{ QUEST_TYPES[type].label }}{{ QUEST_TYPES[type].comingSoon ? ' (coming soon)' : '' }}
          </option>
        </select>
        <p class="field-hint type-description">
          {{ selectedType.description }}
          <span class="help-app">Participants use: {{ selectedType.helpApp }}.</span>
        </p>
      </div>

      <div class="criteria-box">
        <!-- OSM / OHM required tags as key = value rows -->
        <template v-if="criteriaType === 'osm_tags' || criteriaType === 'ohm_feature'">
          <label class="form-label">Required tags</label>
          <p class="field-hint">Use <code>*</code> (or leave the value blank) to accept any value.</p>
          <div
            v-for="(row, index) in (criteriaType === 'osm_tags' ? rules.osmTags : rules.ohmTags)"
            :key="index"
            class="tag-row"
          >
            <input v-model="row.key" type="text" class="form-input tag-key" placeholder="key" aria-label="Tag key" />
            <span class="tag-eq">=</span>
            <input v-model="row.value" type="text" class="form-input tag-value" placeholder="*" aria-label="Tag value" />
            <button
              type="button"
              class="btn btn-outline btn-icon"
              aria-label="Remove tag"
              @click="removeTagRow(criteriaType === 'osm_tags' ? rules.osmTags : rules.ohmTags, index)"
            >✕</button>
          </div>
          <button
            type="button"
            class="btn btn-outline btn-small add-tag"
            @click="addTagRow(criteriaType === 'osm_tags' ? rules.osmTags : rules.ohmTags)"
          >+ Add tag</button>
        </template>

        <template v-if="criteriaType === 'osm_tags'">
          <div v-if="targetCoords" class="form-group">
            <label class="form-label" for="osmRadius">Match radius around the target (m)</label>
            <input id="osmRadius" v-model.number="rules.osmRadiusM" type="number" min="1" class="form-input" />
          </div>
          <label class="checkbox-row">
            <input v-model="rules.requireHashtag" type="checkbox" />
            Require the event hashtag on the changeset
          </label>
        </template>

        <div v-if="criteriaType === 'wikimedia_commons'" class="form-group">
          <label class="form-label" for="wikiCategory">Commons category <span class="optional">(optional)</span></label>
          <input id="wikiCategory" v-model="rules.category" type="text" class="form-input" placeholder="e.g. Murals in San Francisco" />
        </div>

        <template v-if="criteriaType === 'wikidata_statement'">
          <div class="form-group">
            <label class="form-label" for="wikidataQid">Wikidata item</label>
            <input id="wikidataQid" v-model="rules.qid" type="text" class="form-input" placeholder="e.g. Q111393295" />
          </div>
          <div class="form-group">
            <label class="form-label" for="wikidataProperties">Properties to add</label>
            <input id="wikidataProperties" v-model="rules.properties" type="text" class="form-input" placeholder="e.g. P84, P571" />
          </div>
        </template>

        <template v-if="criteriaType === 'oss_contribution'">
          <span class="form-label">Counts</span>
          <div class="checkbox-inline">
            <label class="checkbox-row"><input v-model="rules.kinds.pr" type="checkbox" /> Pull requests</label>
            <label class="checkbox-row"><input v-model="rules.kinds.issue" type="checkbox" /> Issues</label>
          </div>
          <div class="form-group">
            <label class="form-label" for="allowedOwners">Allowed GitHub owners <span class="optional">(optional)</span></label>
            <input id="allowedOwners" v-model="rules.allowedOwners" type="text" class="form-input" placeholder="e.g. OSGeo, qgis, OSGeo-GDAL (blank = any)" />
          </div>
        </template>

        <template v-if="criteriaType === 'location_checkin'">
          <div class="form-group">
            <label class="form-label" for="checkinRadius">Check-in radius (m)</label>
            <input id="checkinRadius" v-model.number="rules.checkinRadiusM" type="number" min="1" class="form-input" />
          </div>
          <div class="form-group">
            <label class="form-label" for="minMinutes">Minimum minutes on site</label>
            <input id="minMinutes" v-model.number="rules.minMinutes" type="number" min="0" class="form-input" />
          </div>
        </template>

        <p v-if="selectedType.comingSoon" class="field-hint coming-soon">
          Coming soon: the server does not verify this type yet, so the quest is saved as inactive.
        </p>

        <div v-if="usesTargetCount" class="form-group target-count">
          <label class="form-label" for="targetCount">Contributions needed to complete</label>
          <input id="targetCount" v-model.number="rules.targetCount" type="number" min="1" class="form-input" />
        </div>
      </div>

      <div class="form-group">
        <label class="form-label" for="pointsReward">Points Reward</label>
        <input id="pointsReward" v-model.number="pointsReward" type="number" min="1" class="form-input" />
      </div>

      <fieldset class="form-group window-fields">
        <legend class="form-label">Quest window <span class="optional">(optional, your local time)</span></legend>
        <div class="window-row">
          <label class="window-label">
            From
            <input v-model="windowStart" type="datetime-local" class="form-input" />
          </label>
          <label class="window-label">
            Until
            <input v-model="windowEnd" type="datetime-local" class="form-input" />
          </label>
        </div>
      </fieldset>

      <!-- Inspired-by session picker -->
      <div class="form-group inspired-picker">
        <span class="form-label">Inspired by <span class="optional">(optional)</span></span>

        <div v-if="chosenSession" class="chosen-session">
          <p class="field-hint">
            <a v-if="inspiredPreview?.url" :href="inspiredPreview.url" target="_blank" rel="noopener">{{ inspiredPreview?.title }}</a>
            <strong v-else>{{ inspiredPreview?.title }}</strong>
            <span v-if="inspiredPreview?.details"> — {{ inspiredPreview.details }}</span>
          </p>
          <button type="button" class="btn btn-outline btn-small" @click="chosenSession = null">Change</button>
        </div>

        <template v-else>
          <p v-if="sessionsState === 'loading'" class="field-hint">Loading sessions…</p>
          <p v-else-if="sessionsState === 'no-schedule'" class="field-hint">
            Set a schedule URL on the event to pick sessions. You can still enter one by hand.
          </p>
          <p v-else-if="sessionsState === 'error'" class="field-hint error-text">{{ sessionsError }}</p>

          <template v-if="sessionsState === 'ready'">
            <input
              v-model="sessionFilter"
              type="search"
              class="form-input"
              placeholder="Filter by title or speaker"
              aria-label="Filter sessions"
            />
            <ul class="session-list">
              <li v-for="session in filteredSessions" :key="session.code || session.title">
                <button type="button" class="session-option" @click="chooseSession(session)">
                  <span class="session-title">{{ session.title }}</span>
                  <span class="session-meta">
                    {{ [(session.speakers || []).join(', '), formatSessionTime(session.start), session.room].filter(Boolean).join(' · ') }}
                  </span>
                </button>
              </li>
              <li v-if="filteredSessions.length === 0" class="field-hint">No sessions match.</li>
            </ul>
          </template>

          <details v-if="sessionsState !== 'loading'" class="manual-session" :open="sessionsState !== 'ready'">
            <summary class="field-hint">Not in the schedule? Enter it by hand</summary>
            <input v-model="manualSession.title" type="text" class="form-input" placeholder="Session or event title" aria-label="Session title" />
            <input v-model="manualSession.url" type="url" class="form-input" placeholder="https:// link (optional)" aria-label="Session link" />
          </details>
        </template>
      </div>

      <div class="target-location-hint">
        <p class="hint-text">
          📍 <strong>Target:</strong>&nbsp;<span v-if="targetCoords">{{ targetCoords.lat.toFixed(4) }}, {{ targetCoords.lng.toFixed(4) }} (drag the pin to adjust)</span>
          <span v-else-if="wholeArea">Whole event area</span>
          <span v-else>Click the map to pin a target point</span>
        </p>
        <label class="checkbox-row">
          <input v-model="wholeArea" type="checkbox" @change="onWholeAreaChange" />
          Use whole event area (no specific target)
        </label>
      </div>

      <button class="btn btn-primary btn-block" :disabled="loading" @click="handleSaveQuest">
        {{ loading ? 'Saving...' : 'Add Quest Challenge' }}
      </button>

      <div class="existing-quests-section">
        <h3>Existing Quests ({{ quests.length }})</h3>
        <ul class="quests-list">
          <li v-for="q in quests" :key="q.id" class="quest-item">
            <div class="quest-item-main">
              <strong>{{ q.title }}</strong>
              <span class="quest-item-meta">
                <span class="type-chip" :style="{ color: `var(${questTypeFor(q.criteria_type).colorToken})` }">
                  {{ questTypeFor(q.criteria_type).icon }} {{ questTypeFor(q.criteria_type).shortLabel }}
                </span>
                · {{ q.points_reward }} pts
                <span v-if="q.is_active === false" class="badge badge-warning">inactive</span>
              </span>
            </div>
            <button type="button" class="btn btn-outline btn-small delete-btn" @click="handleDeleteQuest(q)">
              Delete
            </button>
          </li>
        </ul>
      </div>
    </div>

    <div class="builder-map-container">
      <div id="builder-map" class="map-viewport"></div>
    </div>
  </div>
</template>

<style scoped>
.host-builder-view {
  display: flex;
  height: calc(100vh - var(--header-height));
  gap: var(--space-4);
  padding: var(--space-4);
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

.builder-sidebar {
  width: 420px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.sidebar-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  margin-bottom: var(--space-1);
}

.sidebar-subtitle {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin-bottom: var(--space-4);
}

.criteria-box {
  background-color: var(--color-bg-subtle);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
}

.target-location-hint {
  background-color: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
  font-size: var(--font-size-xs);
}

.btn-block {
  width: 100%;
}

.builder-map-container {
  flex: 1;
  height: 100%;
}

.existing-quests-section {
  margin-top: var(--space-6);
  border-top: 1px solid var(--color-border);
  padding-top: var(--space-4);
}

.quests-list {
  list-style: none;
  margin-top: var(--space-2);
}

.quest-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-sm);
}

.quest-item-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.quest-item-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.type-chip {
  font-weight: var(--font-weight-semibold);
}

.delete-btn {
  flex-shrink: 0;
  color: var(--color-danger);
}

.field-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-top: var(--space-1);
}

.help-app {
  display: block;
  color: var(--color-text-subtle);
}

.optional {
  color: var(--color-text-muted);
  font-weight: var(--font-weight-normal);
}

.error-text {
  color: var(--color-danger);
}

.coming-soon {
  color: var(--color-warning);
  margin-bottom: var(--space-2);
}

.tag-row {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  margin-top: var(--space-2);
}

.tag-row .form-input {
  min-width: 0;
  font-family: var(--font-family-mono);
  font-size: var(--font-size-sm);
}

.tag-eq {
  color: var(--color-text-muted);
}

.btn-icon {
  padding: var(--space-1) var(--space-2);
  flex-shrink: 0;
}

.btn-small {
  padding: var(--space-1) var(--space-2);
  font-size: var(--font-size-xs);
}

.add-tag {
  margin: var(--space-2) 0 var(--space-3);
}

.checkbox-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-sm);
  margin-bottom: var(--space-2);
}

.checkbox-inline {
  display: flex;
  gap: var(--space-4);
}

.target-count {
  margin-bottom: 0;
}

.window-fields {
  border: none;
}

.window-row {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.window-label {
  flex: 1 1 160px;
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.inspired-picker {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.chosen-session {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
  background-color: var(--color-bg-subtle);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
}

.chosen-session .field-hint {
  margin-top: 0;
  color: var(--color-text-main);
}

.session-list {
  list-style: none;
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.session-option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
  text-align: left;
  padding: var(--space-2) var(--space-3);
  background: none;
  border: none;
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  color: var(--color-text-main);
}

.session-option:hover,
.session-option:focus-visible {
  background-color: var(--color-primary-light);
}

.session-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
}

.session-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.manual-session {
  display: flex;
  flex-direction: column;
}

.manual-session summary {
  cursor: pointer;
}

.manual-session .form-input {
  margin-top: var(--space-2);
}

/* Phone width: map on top (needed for pinning targets), form below */
@media (max-width: 768px) {
  .host-builder-view {
    flex-direction: column;
    height: auto;
    padding: var(--space-2);
  }

  .builder-sidebar {
    width: 100%;
    overflow: visible;
    padding: var(--space-4);
  }

  .builder-map-container {
    order: -1;
    flex: none;
    height: 45vh;
  }

  .builder-map-container .map-viewport {
    min-height: 0;
  }
}

.alert {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-3);
  font-size: var(--font-size-xs);
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
</style>
