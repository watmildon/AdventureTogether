<script setup lang="ts">
/**
 * Back-office event form, for both /backoffice/events/new and /backoffice/events/:id/edit.
 *
 * The perimeter is a rectangle drawn without plugins: click two opposite corners on the map
 * (or type west/south/east/north). Inputs and the drawn rectangle stay in sync, and the
 * rectangle is saved as a closed GeoJSON Polygon in lon/lat order (see perimeter.ts).
 * A non-rectangular perimeter loaded for editing is shown as-is and kept unless redrawn.
 */
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import L from 'leaflet'
import { api, ApiError, type EventData } from '../../api'
import {
  bboxFromCorners,
  bboxToInputs,
  bboxToPolygon,
  parseBboxInputs,
  polygonToBbox,
  type Bbox,
  type BboxInputs
} from '../../composables/perimeter'
import { localInputToIso, isoToLocalInput, normaliseHashtag, SCHEDULE_URL_HOSTS } from '../../composables/eventForm'

const route = useRoute()
const router = useRouter()
const eventId = route.params.id as string | undefined
const isEdit = Boolean(eventId)

const form = reactive({
  title: '',
  slug: '',
  description: '',
  hashtag: '',
  start: '',
  end: '',
  scheduleUrl: '',
  isActive: true
})

const bboxInputs = reactive<BboxInputs>({ west: '', south: '', east: '', north: '' })
const parsedBbox = computed(() => parseBboxInputs(bboxInputs))

/** The loaded perimeter when it is not a rectangle; kept on save unless the host draws a new one. */
const keptPolygon = ref<any | null>(null)
/** The inputs as loaded, to tell whether a rectangular perimeter was changed. */
let loadedInputs = ''

const loading = ref(isEdit)
const saving = ref(false)
const loadError = ref<string | null>(null)
/** Per-field messages, keyed like the API's fields (title, hashtag, bounding_polygon...). */
const errors = ref<Record<string, string[]>>({})
const generalError = ref<string | null>(null)

const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone

// Leaflet state (not reactive: Leaflet objects must not be proxied)
let map: L.Map | null = null
let rectangleLayer: L.Rectangle | null = null
let previewLayer: L.Rectangle | null = null
let cornerMarker: L.CircleMarker | null = null
let keptLayer: L.GeoJSON | null = null
/** First corner of a rectangle being drawn, or null when not drawing. */
const cornerA = ref<L.LatLng | null>(null)

const rectStyle: L.PathOptions = { color: '#2563eb', weight: 3, dashArray: '6, 6', fillColor: '#3b82f6', fillOpacity: 0.1, interactive: false }

const drawHint = computed(() => {
  if (cornerA.value) return 'Now click the opposite corner.'
  if (parsedBbox.value.bbox) return 'Click two new corners to redraw, or edit the numbers.'
  return 'Click two opposite corners on the map.'
})

/** Draws (or moves) the dashed rectangle for the current inputs, dimming a kept perimeter it replaces. */
const syncRectangle = (bbox: Bbox | null) => {
  if (!map) return
  if (!bbox) {
    rectangleLayer?.remove()
    rectangleLayer = null
  } else {
    const bounds = L.latLngBounds([bbox.south, bbox.west], [bbox.north, bbox.east])
    if (rectangleLayer) rectangleLayer.setBounds(bounds)
    else rectangleLayer = L.rectangle(bounds, rectStyle).addTo(map)
  }
  keptLayer?.setStyle({ opacity: bbox ? 0.3 : 1, fillOpacity: bbox ? 0.02 : 0.1 })
}

watch(() => parsedBbox.value.bbox, syncRectangle)

/** Zooms to the typed bbox once the host leaves an input (not on every keystroke). */
const fitToInputs = () => {
  const bbox = parsedBbox.value.bbox
  if (map && bbox) map.fitBounds([[bbox.south, bbox.west], [bbox.north, bbox.east]], { padding: [20, 20] })
}

const clearCorner = () => {
  cornerA.value = null
  cornerMarker?.remove()
  cornerMarker = null
  previewLayer?.remove()
  previewLayer = null
}

/** Rectangle tool: first click sets corner A, second sets corner B and fills the inputs. */
const onMapClick = (e: L.LeafletMouseEvent) => {
  if (!map) return
  if (!cornerA.value) {
    cornerA.value = e.latlng
    cornerMarker = L.circleMarker(e.latlng, { radius: 5, color: '#2563eb', fillColor: '#2563eb', fillOpacity: 1, interactive: false }).addTo(map)
    return
  }
  const bbox = bboxFromCorners(cornerA.value, e.latlng)
  clearCorner()
  // Two clicks on the same spot give a zero-size box; ignore rather than show an error
  if (bbox.west === bbox.east || bbox.south === bbox.north) return
  Object.assign(bboxInputs, bboxToInputs(bbox))
}

/** Rubber-band preview between corner A and the pointer. */
const onMapMove = (e: L.LeafletMouseEvent) => {
  if (!map || !cornerA.value) return
  const bounds = L.latLngBounds(cornerA.value, e.latlng)
  if (previewLayer) previewLayer.setBounds(bounds)
  else previewLayer = L.rectangle(bounds, { ...rectStyle, weight: 2, fillOpacity: 0.05 }).addTo(map)
}

const clearPerimeter = () => {
  clearCorner()
  Object.assign(bboxInputs, { west: '', south: '', east: '', north: '' })
}

const initMap = () => {
  map = L.map('perimeter-map', { doubleClickZoom: false }).setView([20, 0], 2)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
  }).addTo(map)
  map.on('click', onMapClick)
  map.on('mousemove', onMapMove)
}

/** Fills the form from an existing event. */
const fillForm = (event: EventData) => {
  Object.assign(form, {
    title: event.title,
    slug: event.slug,
    description: event.description || '',
    hashtag: event.hashtag,
    start: isoToLocalInput(event.start_time),
    end: isoToLocalInput(event.end_time),
    scheduleUrl: event.schedule_url || '',
    isActive: event.is_active
  })

  const bbox = polygonToBbox(event.bounding_polygon)
  if (bbox) {
    Object.assign(bboxInputs, bboxToInputs(bbox))
    loadedInputs = JSON.stringify(bboxToInputs(bbox))
    syncRectangle(bbox)
    fitToInputs()
  } else if (event.bounding_polygon && map) {
    keptPolygon.value = event.bounding_polygon
    keptLayer = L.geoJSON(event.bounding_polygon, { interactive: false, style: { ...rectStyle, dashArray: undefined, color: '#64748b', fillColor: '#94a3b8' } }).addTo(map)
    map.fitBounds(keptLayer.getBounds(), { padding: [20, 20] })
  }
}

/** Client-side checks mirroring the API's required fields, so obvious gaps show before a round trip. */
const validate = (): Record<string, string[]> => {
  const found: Record<string, string[]> = {}
  if (!form.title.trim()) found.title = ['Give the event a title.']
  if (!normaliseHashtag(form.hashtag)) found.hashtag = ['Give the event a hashtag.']
  const start = localInputToIso(form.start)
  const end = localInputToIso(form.end)
  if (!start) found.start_time = ['Set a start date and time.']
  if (!end) found.end_time = ['Set an end date and time.']
  if (start && end && new Date(end) <= new Date(start)) found.end_time = ['The end must be after the start.']
  if (parsedBbox.value.error) found.bounding_polygon = [parsedBbox.value.error]
  else if (!parsedBbox.value.bbox && !keptPolygon.value) found.bounding_polygon = ['Draw the event perimeter on the map or type its edges.']
  return found
}

/** The request body. On edit, the perimeter is only sent when the host changed it. */
const buildPayload = (): Partial<EventData> => {
  const payload: Partial<EventData> = {
    title: form.title.trim(),
    description: form.description,
    hashtag: normaliseHashtag(form.hashtag),
    start_time: localInputToIso(form.start)!,
    end_time: localInputToIso(form.end)!,
    schedule_url: form.scheduleUrl.trim(),
    is_active: form.isActive
  }
  // Slug is optional on create (the server derives one from the title) and fixed afterwards
  if (!isEdit && form.slug.trim()) payload.slug = form.slug.trim()

  const bbox = parsedBbox.value.bbox
  const changed = JSON.stringify({ ...bboxInputs }) !== loadedInputs
  if (bbox && (!isEdit || changed)) payload.bounding_polygon = bboxToPolygon(bbox)
  return payload
}

const save = async () => {
  generalError.value = null
  errors.value = validate()
  if (Object.keys(errors.value).length) return

  saving.value = true
  try {
    const payload = buildPayload()
    const saved = isEdit ? await api.updateEvent(eventId!, payload) : await api.createEvent(payload)
    router.push(`/backoffice/events/${saved.id}`)
  } catch (err: any) {
    if (err instanceof ApiError && Object.keys(err.fields).length) {
      const { non_field_errors, detail, ...fields } = err.fields
      errors.value = fields
      const general = [...(non_field_errors || []), ...(detail || [])]
      generalError.value = general.length ? general.join(' ') : 'Please fix the highlighted fields.'
    } else {
      generalError.value = err?.message || 'Saving the event failed.'
    }
  } finally {
    saving.value = false
  }
}

/** Fields the API may report that have no input of their own, shown in the general box instead. */
const unplacedErrors = computed(() => {
  const placed = new Set(['title', 'slug', 'description', 'hashtag', 'start_time', 'end_time', 'schedule_url', 'is_active', 'bounding_polygon'])
  return Object.entries(errors.value).filter(([field]) => !placed.has(field))
})

onMounted(async () => {
  initMap()
  if (!isEdit) return
  try {
    fillForm(await api.getEvent(eventId!))
  } catch {
    loadError.value = `Could not load event ${eventId}.`
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  map?.remove()
  map = null
})
</script>

<template>
  <div class="event-form-view">
    <p class="breadcrumb">
      <RouterLink to="/backoffice">Events</RouterLink>
      <template v-if="isEdit"> / <RouterLink :to="`/backoffice/events/${eventId}`">{{ form.title || `Event ${eventId}` }}</RouterLink></template>
    </p>
    <h1 class="page-title">{{ isEdit ? 'Edit event' : 'New event' }}</h1>

    <div v-if="loadError" class="alert alert-danger">{{ loadError }}</div>
    <div v-if="generalError" class="alert alert-danger" role="alert">
      {{ generalError }}
      <ul v-if="unplacedErrors.length" class="unplaced">
        <li v-for="[field, messages] in unplacedErrors" :key="field">{{ field }}: {{ messages.join(' ') }}</li>
      </ul>
    </div>

    <form class="card event-form" novalidate @submit.prevent="save">
      <div class="form-grid">
        <div class="form-group span-2">
          <label class="form-label" for="eventTitle">Title</label>
          <input id="eventTitle" v-model="form.title" type="text" class="form-input" :class="{ invalid: errors.title }" placeholder="e.g. FOSS4G NA 2026 Open Data Hunt" />
          <p v-for="msg in errors.title" :key="msg" class="field-error">{{ msg }}</p>
        </div>

        <div class="form-group">
          <label class="form-label" for="eventSlug">Slug <span class="optional">{{ isEdit ? '(fixed)' : '(optional)' }}</span></label>
          <input id="eventSlug" v-model="form.slug" type="text" class="form-input" :readonly="isEdit" :class="{ invalid: errors.slug }" :placeholder="isEdit ? '' : 'made from the title if blank'" autocapitalize="off" />
          <p v-for="msg in errors.slug" :key="msg" class="field-error">{{ msg }}</p>
        </div>

        <div class="form-group">
          <label class="form-label" for="eventHashtag">Hashtag</label>
          <div class="hashtag-input">
            <span class="hash">#</span>
            <input id="eventHashtag" v-model="form.hashtag" type="text" class="form-input" :class="{ invalid: errors.hashtag }" placeholder="FOSS4GNA2026" autocapitalize="off" @blur="form.hashtag = normaliseHashtag(form.hashtag)" />
          </div>
          <p class="field-hint">Participants put this in changeset comments, upload descriptions and PRs.</p>
          <p v-for="msg in errors.hashtag" :key="msg" class="field-error">{{ msg }}</p>
        </div>

        <div class="form-group span-2">
          <label class="form-label" for="eventDescription">Description</label>
          <textarea id="eventDescription" v-model="form.description" class="form-textarea" rows="3" :class="{ invalid: errors.description }" placeholder="What participants will do, and where."></textarea>
          <p v-for="msg in errors.description" :key="msg" class="field-error">{{ msg }}</p>
        </div>

        <div class="form-group">
          <label class="form-label" for="eventStart">Starts</label>
          <input id="eventStart" v-model="form.start" type="datetime-local" class="form-input" :class="{ invalid: errors.start_time }" />
          <p v-for="msg in errors.start_time" :key="msg" class="field-error">{{ msg }}</p>
        </div>

        <div class="form-group">
          <label class="form-label" for="eventEnd">Ends</label>
          <input id="eventEnd" v-model="form.end" type="datetime-local" class="form-input" :class="{ invalid: errors.end_time }" />
          <p v-for="msg in errors.end_time" :key="msg" class="field-error">{{ msg }}</p>
        </div>
        <p class="field-hint span-2 tz-hint">Times are in your time zone ({{ timeZone }}).</p>

        <div class="form-group span-2">
          <label class="form-label" for="eventSchedule">Schedule URL <span class="optional">(optional)</span></label>
          <input id="eventSchedule" v-model="form.scheduleUrl" type="url" class="form-input" :class="{ invalid: errors.schedule_url }" placeholder="https://talks.osgeo.org/<event>/schedule/export/schedule.json" autocapitalize="off" />
          <p class="field-hint">
            A pretalx/frab schedule JSON export, used to pick the talk behind each quest. Must be an https link on
            {{ SCHEDULE_URL_HOSTS.join(' or ') }} (or a subdomain).
          </p>
          <p v-for="msg in errors.schedule_url" :key="msg" class="field-error">{{ msg }}</p>
        </div>

        <label class="checkbox span-2">
          <input v-model="form.isActive" type="checkbox" />
          Active <span class="optional">(inactive events are hidden from participants and not harvested)</span>
        </label>
      </div>

      <fieldset class="perimeter">
        <legend class="form-label">Perimeter</legend>
        <p class="field-hint">
          {{ drawHint }}
          <button v-if="cornerA" type="button" class="link-btn" @click="clearCorner">Cancel</button>
          <button v-else-if="parsedBbox.bbox" type="button" class="link-btn" @click="clearPerimeter">Clear</button>
        </p>
        <p v-if="keptPolygon" class="kept-note">
          {{ parsedBbox.bbox ? 'The new rectangle will replace the current perimeter (grey).' : 'The current perimeter (grey) is not a rectangle. It is kept unless you draw a new one.' }}
        </p>

        <div class="perimeter-map-wrap">
          <div id="perimeter-map" class="map-viewport perimeter-map" :class="{ drawing: cornerA }"></div>
        </div>

        <div class="bbox-grid">
          <div v-for="edge in (['west', 'south', 'east', 'north'] as const)" :key="edge" class="form-group">
            <label class="form-label" :for="`bbox-${edge}`">{{ edge[0].toUpperCase() + edge.slice(1) }}</label>
            <input :id="`bbox-${edge}`" v-model="bboxInputs[edge]" type="number" step="any" class="form-input" :placeholder="edge === 'west' || edge === 'east' ? 'longitude' : 'latitude'" @change="fitToInputs" />
          </div>
        </div>
        <p v-for="msg in errors.bounding_polygon" :key="msg" class="field-error">{{ msg }}</p>
      </fieldset>

      <div class="form-actions">
        <button type="submit" class="btn btn-primary" :disabled="saving || loading">
          {{ saving ? 'Saving...' : isEdit ? 'Save changes' : 'Create event' }}
        </button>
        <RouterLink :to="isEdit ? `/backoffice/events/${eventId}` : '/backoffice'" class="btn btn-outline">Cancel</RouterLink>
      </div>
    </form>
  </div>
</template>

<style scoped>
.event-form-view {
  max-width: 960px;
  margin: 0 auto;
  padding: var(--space-6) var(--space-4) var(--space-10);
  width: 100%;
}

.breadcrumb {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin-bottom: var(--space-1);
}

.page-title {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  margin-bottom: var(--space-4);
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 var(--space-4);
}

.span-2 {
  grid-column: span 2;
}

.optional {
  color: var(--color-text-muted);
  font-weight: var(--font-weight-normal);
  font-size: var(--font-size-xs);
}

/* Textareas default to a monospace font in some browsers */
.form-textarea {
  font-family: inherit;
}

.form-input[readonly] {
  background-color: var(--color-bg-subtle);
  color: var(--color-text-muted);
}

.hashtag-input {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.hash {
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-muted);
}

.field-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-top: var(--space-1);
}

.tz-hint {
  margin: calc(-1 * var(--space-2)) 0 var(--space-4);
}

.field-error {
  font-size: var(--font-size-xs);
  color: var(--color-danger);
  margin-top: var(--space-1);
}

.invalid {
  border-color: var(--color-danger);
}

.checkbox {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-sm);
  margin-bottom: var(--space-4);
}

.perimeter {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-4);
}

.perimeter legend {
  padding: 0 var(--space-1);
}

.kept-note {
  font-size: var(--font-size-xs);
  color: var(--color-warning);
  margin-top: var(--space-1);
}

.perimeter-map-wrap {
  height: 380px;
  margin: var(--space-3) 0;
}

.perimeter-map {
  min-height: 0;
}

.perimeter-map.drawing {
  cursor: crosshair;
}

.bbox-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-3);
}

.link-btn {
  background: none;
  border: none;
  color: var(--color-primary);
  cursor: pointer;
  font-size: inherit;
  padding: 0 var(--space-1);
  text-decoration: underline;
}

.form-actions {
  display: flex;
  gap: var(--space-2);
}

.alert {
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
  font-size: var(--font-size-sm);
}

.alert-danger {
  background-color: var(--color-danger-light);
  color: var(--color-danger);
  border: 1px solid var(--color-danger-border);
}

.unplaced {
  margin: var(--space-1) 0 0 var(--space-4);
}

@media (max-width: 640px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .span-2 {
    grid-column: auto;
  }

  .bbox-grid {
    grid-template-columns: 1fr 1fr;
  }

  .perimeter-map-wrap {
    height: 300px;
  }
}
</style>
