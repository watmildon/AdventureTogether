<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import L from 'leaflet'
import { api, type EventData, type QuestData, type LocationPingData, type PingCheckin } from '../api'
import { useGeolocation, clearSimulatedPosition, type VisibilityTier } from '../composables/useGeolocation'
import { useDeepLinks } from '../composables/useDeepLinks'
import { useQuestProgress, readStoredTeamId } from '../composables/useQuestProgress'
import { createQuestLayer, questPopupHtml, focusQuestLayer } from '../composables/questLayers'
import QuestPanel from '../components/QuestPanel.vue'
import LeaderboardList from '../components/LeaderboardList.vue'

const route = useRoute()
const eventId = route.params.id as string

const event = ref<EventData | null>(null)
const quests = ref<QuestData[]>([])
const activeLocations = ref<LocationPingData[]>([])

// Composable instances
const {
  coords,
  accuracy,
  isForeground,
  visibility,
  isTracking,
  isSimulated,
  error: geoError,
  lastPingTime,
  lastPing,
  userIdentifier,
  setVisibility
} = useGeolocation(eventId)

/** Drops the simulated GPS position and reloads so the real Geolocation API takes over. */
const stopSimulatingGps = () => {
  clearSimulatedPosition()
  const url = new URL(window.location.href)
  url.searchParams.delete('lat')
  url.searchParams.delete('lng')
  window.location.href = url.toString()
}

const { getDeepLinks, launchDeepLink } = useDeepLinks()

// Team progress and leaderboard (polled every 30 s). The team id comes from JoinTeamView's
// localStorage record, or later from the ping response if the participant joined elsewhere.
const teamId = ref<number | null>(readStoredTeamId(eventId))
const {
  progressByQuest,
  leaderboard,
  error: leaderboardError,
  refresh: refreshProgressAndLeaderboard,
  refreshProgress,
  startPolling: startProgressPolling
} = useQuestProgress(eventId, teamId)

const teamName = computed(() =>
  leaderboard.value.find((t) => t.id === teamId.value)?.name || localStorage.getItem('team_name') || null
)

/** Participants hide inactive quests; hosts still see them in the builder. */
const visibleQuests = computed(() => quests.value.filter((q) => q.is_active !== false))

/** Other participants only: the server also returns our own latest ping. */
const teammates = computed(() => activeLocations.value.filter((loc) => loc.user_identifier !== userIdentifier))

// Check-in state per quest id. 'verified' is sticky; 'in_range' reflects the latest ping.
const checkins = ref<Record<number, 'in_range' | 'verified'>>({})
const checkinToast = ref<{ text: string; questId: number } | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null

let map: L.Map | null = null
let perimeterLayer: L.GeoJSON | null = null
let selfMarker: L.CircleMarker | null = null
let selfAccuracyCircle: L.Circle | null = null
let teammateMarkersGroup: L.LayerGroup | null = null
let questsLayerGroup: L.LayerGroup | null = null
const questLayers = new Map<number, L.Layer>()
let pollTimer: any = null

const deepLinks = computed(() => {
  if (coords.value) {
    return getDeepLinks(coords.value.lat, coords.value.lng)
  }
  return null
})

const formatTimeAgo = (dateStr: string) => {
  const diffMs = Date.now() - new Date(dateStr).getTime()
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 1) return 'Just now'
  if (diffMins === 1) return '1 min ago'
  return `${diffMins} mins ago`
}

/** "2/5" for popups when the participant has a team, otherwise null. */
const progressTextFor = (quest: QuestData): string | null => {
  if (!teamId.value) return null
  const row = progressByQuest.value.get(quest.id)
  return `${row?.count ?? 0}/${row?.target_count ?? quest.target_count ?? 1}`
}

const initMap = async () => {
  const mapElement = document.getElementById('map')
  if (!mapElement) return

  map = L.map('map').setView([37.7749, -122.4194], 14)

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
  }).addTo(map)

  questsLayerGroup = L.layerGroup().addTo(map)
  teammateMarkersGroup = L.layerGroup().addTo(map)

  // GPS may have resolved before the map existed (simulated positions resolve instantly)
  updateSelfMarker()

  await loadEventAndQuests()
  await pollActiveLocations()
  loadCheckins()
  refreshProgressAndLeaderboard()

  // Poll teammate locations every 8 seconds; progress and leaderboard every 30 seconds
  pollTimer = setInterval(pollActiveLocations, 8000)
  startProgressPolling()
}

const loadEventAndQuests = async () => {
  try {
    event.value = await api.getEvent(eventId)
    quests.value = await api.getQuests(eventId)

    // Render Event Perimeter
    if (event.value && event.value.bounding_polygon && map) {
      if (perimeterLayer) map.removeLayer(perimeterLayer)

      perimeterLayer = L.geoJSON(event.value.bounding_polygon, {
        style: {
          color: '#2563eb',
          weight: 3,
          dashArray: '6, 6',
          fillColor: '#3b82f6',
          fillOpacity: 0.08
        }
      }).addTo(map)

      map.fitBounds(perimeterLayer.getBounds(), { padding: [30, 30] })
    }

    renderQuestLayers()
  } catch (err: any) {
    // Event load error
  }
}

/** Quest targets: points as type-coloured markers, polygons as light outlines. */
const renderQuestLayers = () => {
  if (!questsLayerGroup) return
  questsLayerGroup.clearLayers()
  questLayers.clear()

  visibleQuests.value.forEach((quest) => {
    const layer = createQuestLayer(quest, questPopupHtml(quest, progressTextFor(quest)))
    if (!layer) return
    questLayers.set(quest.id, layer)
    questsLayerGroup?.addLayer(layer)
  })

  // Keep the participant's own marker above quest markers
  selfMarker?.bringToFront()
}

// Refresh popup text in place when progress changes, so an open popup is not closed by a re-render
watch(progressByQuest, () => {
  visibleQuests.value.forEach((quest) => {
    questLayers.get(quest.id)?.setPopupContent(questPopupHtml(quest, progressTextFor(quest)))
  })
})

/** "Show on map": pan to the quest's target and open its popup (scrolling the map into view on phones). */
const showQuestOnMap = (quest: QuestData) => {
  const layer = questLayers.get(quest.id)
  if (!map || !layer) return
  document.getElementById('map')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  focusQuestLayer(map, layer)
}

const pollActiveLocations = async () => {
  if (!map || !teammateMarkersGroup) return

  try {
    const locations = await api.getActiveLocations(eventId, userIdentifier)
    activeLocations.value = locations

    teammateMarkersGroup.clearLayers()

    locations.forEach((loc) => {
      // Don't render self as teammate marker
      if (loc.user_identifier === userIdentifier) return

      const marker = L.circleMarker([loc.latitude, loc.longitude], {
        radius: 7,
        fillColor: '#0d9488',
        color: '#ffffff',
        weight: 2,
        fillOpacity: 0.85
      }).bindPopup(`
        <b>${loc.display_name}</b><br/>
        Team: ${loc.team_name || 'Individual'}<br/>
        Last seen: ${formatTimeAgo(loc.recorded_at)}
      `)

      teammateMarkersGroup?.addLayer(marker)
    })
  } catch (err: any) {
    // Ignore polling errors
  }
}

/**
 * Draws (or moves) the participant's own position: a solid blue dot with a white ring,
 * plus a faint accuracy circle, distinct from the smaller teal teammate markers.
 */
const updateSelfMarker = () => {
  if (!map || !coords.value) return
  const latLng: L.LatLngExpression = [coords.value.lat, coords.value.lng]

  if (!selfMarker) {
    selfAccuracyCircle = L.circle(latLng, {
      radius: accuracy.value ?? 0,
      color: '#2563eb',
      weight: 1,
      opacity: 0.4,
      fillColor: '#2563eb',
      fillOpacity: 0.1,
      interactive: false
    }).addTo(map)
    selfMarker = L.circleMarker(latLng, {
      radius: 9,
      fillColor: '#2563eb',
      color: '#ffffff',
      weight: 3,
      fillOpacity: 1
    }).bindPopup('<b>You are here</b><br/>Sharing GPS location')
    selfMarker.addTo(map)
  } else {
    selfMarker.setLatLng(latLng)
    selfAccuracyCircle?.setLatLng(latLng)
    selfAccuracyCircle?.setRadius(accuracy.value ?? 0)
  }
}

watch(coords, updateSelfMarker)

const showCheckinToast = (questId: number, title: string) => {
  checkinToast.value = { text: `You're at ${title}`, questId }
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (checkinToast.value = null), 6000)
}

/**
 * Applies the `checkins` list from a ping response. Toasts the first time we see the
 * participant at a quest and refreshes team progress when a check-in becomes verified.
 */
const applyPingCheckins = (list: PingCheckin[] | undefined) => {
  if (!Array.isArray(list)) return
  const next: Record<number, 'in_range' | 'verified'> = {}
  // Verified check-ins stay; in-range ones are replaced by what this ping reports
  for (const [id, status] of Object.entries(checkins.value)) {
    if (status === 'verified') next[Number(id)] = status
  }

  let newlyVerified = false
  for (const checkin of list) {
    if (!checkin || typeof checkin.quest !== 'number') continue
    if (checkin.status !== 'in_range' && checkin.status !== 'verified') continue
    const previous = checkins.value[checkin.quest]
    if (previous === 'verified') continue

    next[checkin.quest] = checkin.status
    if (checkin.status === 'verified') newlyVerified = true
    if (!previous) {
      const title = checkin.quest_title || quests.value.find((q) => q.id === checkin.quest)?.title || 'a quest'
      showCheckinToast(checkin.quest, title)
    }
  }

  checkins.value = next
  if (newlyVerified) refreshProgress()
}

watch(lastPing, (ping) => {
  if (!ping) return
  applyPingCheckins(ping.checkins)
  // The server resolves our team from the membership table; use it if localStorage had none
  if (!teamId.value && ping.team) teamId.value = ping.team
})

/** Marks quests the participant already checked in to (e.g. before a reload). */
const loadCheckins = async () => {
  try {
    const recorded = await api.getCheckins(eventId, userIdentifier)
    const next = { ...checkins.value }
    recorded.forEach((c) => {
      // A revoked check-in (is_verified false) does not count
      if (typeof c?.quest === 'number' && c.is_verified !== false) next[c.quest] = 'verified'
    })
    checkins.value = next
  } catch {
    // Check-ins are optional; older servers do not have the endpoint
  }
}

const focusToastQuest = () => {
  const quest = quests.value.find((q) => q.id === checkinToast.value?.questId)
  if (quest) showQuestOnMap(quest)
}

onMounted(() => {
  initMap()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (toastTimer) clearTimeout(toastTimer)
  map?.remove()
})
</script>

<template>
  <div class="event-map-view">
    <div class="map-header">
      <div class="header-left">
        <h2 class="event-title">{{ event ? event.title : `Event #${eventId}` }}</h2>
        <span v-if="event" class="badge badge-primary">#{{ event.hashtag }}</span>
      </div>

      <div class="header-right">
        <!-- Foreground & GPS Status Indicators -->
        <span :class="['badge', isForeground ? 'badge-success' : 'badge-warning']">
          {{ isForeground ? '● Foreground Active' : '⏸ Background Paused' }}
        </span>

        <!-- Dev/testing aid: shown only when a simulated GPS position is in use -->
        <span v-if="isSimulated" class="badge badge-warning simulated-badge" title="Position comes from ?lat=&lng= / localStorage, not the device GPS">
          🧪 Simulated GPS
          <button type="button" class="simulated-clear" @click="stopSimulatingGps">clear</button>
        </span>

        <!-- Privacy Visibility Selector -->
        <div class="privacy-select-group">
          <label class="privacy-label">Share Location:</label>
          <select
            :value="visibility"
            class="form-select privacy-select"
            @change="setVisibility(($event.target as HTMLSelectElement).value as VisibilityTier)"
          >
            <option value="nobody">Nobody</option>
            <option value="team">Team Only</option>
            <option value="quest">Whole Quest</option>
          </select>
        </div>
      </div>
    </div>

    <div class="map-layout">
      <div class="map-container">
        <div id="map" class="map-viewport"></div>

        <!-- Check-in feedback from the latest location ping -->
        <button
          v-if="checkinToast"
          type="button"
          class="checkin-toast"
          role="status"
          @click="focusToastQuest"
        >
          📍 {{ checkinToast.text }}
        </button>
      </div>

      <!-- Quests, leaderboard, mapping tools and teammates -->
      <aside class="map-sidebar card">
        <div class="sidebar-section">
          <h3 class="section-title">Quests ({{ visibleQuests.length }})</h3>
          <p v-if="teamId" class="section-desc">
            Progress for <strong>{{ teamName || `team #${teamId}` }}</strong>
          </p>
          <p v-else class="section-desc">
            <RouterLink :to="`/events/${eventId}/join`">Join a team</RouterLink> to track progress and earn points.
          </p>
          <QuestPanel
            :quests="visibleQuests"
            :progress-by-quest="progressByQuest"
            :has-team="Boolean(teamId)"
            :checkins="checkins"
            @show-on-map="showQuestOnMap"
          />
        </div>

        <div class="sidebar-section">
          <h3 class="section-title">Leaderboard</h3>
          <p v-if="leaderboardError" class="section-desc">{{ leaderboardError }}</p>
          <p v-else-if="leaderboard.length === 0" class="section-desc">No teams yet.</p>
          <LeaderboardList v-else :entries="leaderboard" :limit="5" :highlight-team-id="teamId" />
        </div>

        <div class="sidebar-section">
          <h3 class="section-title">Mapping Tool Deep Links</h3>
          <p class="section-desc">Tap to launch external mapping editors centered at your GPS location:</p>

          <div v-if="deepLinks" class="deep-links-stack">
            <a
              :href="deepLinks.streetCompleteUrl"
              class="btn btn-primary btn-block deep-link-btn"
              @click.prevent="launchDeepLink(deepLinks.streetCompleteUrl, deepLinks.osmWebEditorUrl)"
            >
              🚀 Open in StreetComplete
            </a>

            <a
              :href="deepLinks.everyDoorUrl"
              class="btn btn-secondary btn-block deep-link-btn"
              @click.prevent="launchDeepLink(deepLinks.everyDoorUrl, deepLinks.osmWebEditorUrl)"
            >
              📍 Open in EveryDoor
            </a>

            <a
              :href="deepLinks.osmWebEditorUrl"
              target="_blank"
              class="btn btn-outline btn-block deep-link-btn"
            >
              🌐 Open OSM Web iD Editor
            </a>
          </div>

          <div v-else class="status-box">
            <p>{{ geoError || 'Waiting for GPS location...' }}</p>
          </div>
        </div>

        <div class="sidebar-section">
          <h3 class="section-title">Active Teammates ({{ teammates.length }})</h3>
          <p v-if="teammates.length === 0" class="section-desc">Nobody else is sharing their location with you right now.</p>
          <ul class="teammate-list">
            <li v-for="loc in teammates" :key="loc.id" class="teammate-item">
              <div>
                <strong>{{ loc.display_name }}</strong>
                <span class="team-subtext">{{ loc.team_name || 'Individual' }}</span>
              </div>
              <span class="time-badge">{{ formatTimeAgo(loc.recorded_at) }}</span>
            </li>
          </ul>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.event-map-view {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--header-height));
  padding: var(--space-4);
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

.map-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-4);
  flex-wrap: wrap;
  gap: var(--space-2);
}

.header-left, .header-right {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.event-title {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
}

.privacy-select-group {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.privacy-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.privacy-select {
  padding: var(--space-1) var(--space-2);
  font-size: var(--font-size-xs);
}

.map-layout {
  display: flex;
  gap: var(--space-4);
  flex: 1;
  overflow: hidden;
}

.map-container {
  flex: 1;
  height: 100%;
  position: relative;
}

/* Keep the map clear of the sticky header when "Show on map" scrolls it into view */
.map-viewport {
  scroll-margin-top: calc(var(--header-height) + var(--space-2));
}

.checkin-toast {
  position: absolute;
  top: var(--space-3);
  left: 50%;
  transform: translateX(-50%);
  /* Above Leaflet panes and controls (z-index up to 1000), below the sticky app header */
  z-index: 999;
  max-width: calc(100% - 2 * var(--space-6));
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-full);
  background-color: var(--color-warning-light);
  color: var(--color-text-main);
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-semibold);
  box-shadow: var(--shadow-md);
  cursor: pointer;
}

.map-sidebar {
  width: 340px;
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  overflow-y: auto;
}

.sidebar-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.section-title {
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
}

.section-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.deep-links-stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.deep-link-btn {
  font-size: var(--font-size-xs);
  padding: var(--space-2);
}

.btn-block {
  width: 100%;
}

.simulated-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.simulated-clear {
  background: transparent;
  border: 1px solid currentColor;
  border-radius: 4px;
  color: inherit;
  cursor: pointer;
  font-size: 0.7rem;
  line-height: 1;
  padding: 0.1rem 0.35rem;
}

.status-box {
  background-color: var(--color-bg-subtle);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--font-size-xs);
  text-align: center;
  color: var(--color-text-muted);
}

.teammate-list {
  list-style: none;
}

.teammate-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--color-border);
  font-size: var(--font-size-xs);
}

.team-subtext {
  display: block;
  font-size: 0.7rem;
  color: var(--color-text-muted);
}

.time-badge {
  color: var(--color-text-muted);
  font-size: 0.7rem;
}

/* Phone width: stack a tall map above the sidebar instead of squeezing both side by side */
@media (max-width: 768px) {
  .event-map-view {
    height: auto;
    padding: var(--space-2);
  }

  .map-header {
    margin-bottom: var(--space-2);
  }

  .map-layout {
    flex-direction: column;
    overflow: visible;
  }

  .map-container {
    flex: none;
    height: 55vh;
    min-height: 55vh;
  }

  .map-container .map-viewport {
    min-height: 0;
  }

  .map-sidebar {
    width: 100%;
    overflow: visible;
    padding: var(--space-4);
  }
}
</style>
