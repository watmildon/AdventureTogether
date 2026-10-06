<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import L from 'leaflet'
import { api, type EventData, type QuestData, type LocationPingData } from '../api'
import { useGeolocation, clearSimulatedPosition, type VisibilityTier } from '../composables/useGeolocation'
import { useDeepLinks } from '../composables/useDeepLinks'

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

const userIdentifier = localStorage.getItem('participant_id') || ''

let map: L.Map | null = null
let perimeterLayer: L.GeoJSON | null = null
let selfMarker: L.CircleMarker | null = null
let teammateMarkersGroup: L.LayerGroup | null = null
let questsLayerGroup: L.LayerGroup | null = null
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

  await loadEventAndQuests()
  await pollActiveLocations()

  // Poll teammate locations every 8 seconds
  pollTimer = setInterval(pollActiveLocations, 8000)
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

    // Render Quest Targets
    if (questsLayerGroup) {
      questsLayerGroup.clearLayers()
      quests.value.forEach((q) => {
        if (q.target_geometry && q.target_geometry.type === 'Point') {
          const [lng, lat] = q.target_geometry.coordinates
          const marker = L.circleMarker([lat, lng], {
            radius: 8,
            fillColor: '#d97706',
            color: '#ffffff',
            weight: 2,
            fillOpacity: 0.9
          }).bindPopup(`<b>${q.title}</b><br/>${q.description}<br/>Reward: ${q.points_reward} pts`)
          questsLayerGroup?.addLayer(marker)
        }
      })
    }
  } catch (err: any) {
    // Event load error
  }
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

// Watch coords and update self marker
const updateSelfMarker = () => {
  if (!map || !coords.value) return

  if (!selfMarker) {
    selfMarker = L.circleMarker([coords.value.lat, coords.value.lng], {
      radius: 9,
      fillColor: '#2563eb',
      color: '#ffffff',
      weight: 3,
      fillOpacity: 1
    }).bindPopup('<b>You are here</b><br/>Sharing GPS location')
    selfMarker.addTo(map)
  } else {
    selfMarker.setLatLng([coords.value.lat, coords.value.lng])
  }
}

onMounted(() => {
  initMap()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
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
      </div>

      <!-- Mapping Tools & Deep Link Sidebar -->
      <aside class="map-sidebar card">
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
          <h3 class="section-title">Active Teammates ({{ activeLocations.length }})</h3>
          <ul class="teammate-list">
            <li v-for="loc in activeLocations" :key="loc.id" class="teammate-item">
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
</style>
