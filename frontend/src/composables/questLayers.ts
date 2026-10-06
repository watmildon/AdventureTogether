/**
 * Leaflet rendering for quest targets, shared by the participant map and the host builder.
 *
 * Point targets become circle markers in the quest type's colour; Polygon (and any other
 * GeoJSON) targets become light outlines so they do not hide the event perimeter or the
 * streets underneath. Popups are built from escaped strings because quest titles and
 * session data are user-entered.
 */

import L from 'leaflet'
import type { QuestData } from '../api'
import { questTypeFor, formatSessionLine, formatQuestWindow } from './useQuestTypes'

/** Escapes text for safe interpolation into Leaflet popup HTML. */
export function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** Popup body: title, type, points, window and the inspired-by line (with link). */
export function questPopupHtml(quest: QuestData, progressText?: string | null): string {
  const type = questTypeFor(quest.criteria_type)
  const window = formatQuestWindow(quest.window_start, quest.window_end)
  const session = formatSessionLine(quest.inspired_by)

  const lines = [
    `<strong>${escapeHtml(quest.title)}</strong>`,
    `<span>${type.icon} ${escapeHtml(type.label)} · ${quest.points_reward} pts</span>`
  ]
  if (progressText) lines.push(`<span>Progress: ${escapeHtml(progressText)}</span>`)
  if (window) lines.push(`<span>🕒 ${escapeHtml(window)}</span>`)
  if (quest.description) lines.push(`<span>${escapeHtml(quest.description)}</span>`)
  if (session) {
    const title = session.url
      ? `<a href="${escapeHtml(session.url)}" target="_blank" rel="noopener">${escapeHtml(session.title)}</a>`
      : escapeHtml(session.title)
    lines.push(`<em>Inspired by: ${title}${session.details ? ` — ${escapeHtml(session.details)}` : ''}</em>`)
  }
  return `<div class="quest-popup">${lines.join('<br/>')}</div>`
}

/**
 * Builds the map layer for a quest target, or null when the quest covers the whole
 * event area (no target geometry).
 *
 * `outlinesInteractive: false` makes polygon outlines ignore clicks. The host builder
 * needs that: Leaflet stops a click that opens a popup, so an interactive polygon
 * would swallow the map click used to pin a new target inside it.
 */
export function createQuestLayer(
  quest: QuestData,
  popupHtml: string,
  { outlinesInteractive = true }: { outlinesInteractive?: boolean } = {}
): L.Layer | null {
  const geometry = quest.target_geometry
  if (!geometry || !geometry.type) return null
  const color = questTypeFor(quest.criteria_type).color

  if (geometry.type === 'Point') {
    const [lng, lat] = geometry.coordinates
    return L.circleMarker([lat, lng], {
      radius: 8,
      fillColor: color,
      color: '#ffffff',
      weight: 2,
      fillOpacity: quest.is_active === false ? 0.4 : 0.9
    }).bindPopup(popupHtml)
  }

  // MultiPoint targets get the same filled dots as Point targets (not image pins); the
  // style function must return them too, since GeoJSON styles override pointToLayer's.
  const pointStyle: L.CircleMarkerOptions = { radius: 7, fillColor: color, color: '#ffffff', weight: 2, opacity: 1, fillOpacity: 0.9 }
  const outlineStyle: L.PathOptions = { color, weight: 2, opacity: 0.8, fillColor: color, fillOpacity: 0.06 }

  return L.geoJSON(geometry, {
    interactive: outlinesInteractive,
    pointToLayer: (_feature, latlng) => L.circleMarker(latlng, pointStyle),
    style: (feature) => (/Point$/.test(feature?.geometry?.type ?? '') ? pointStyle : outlineStyle)
  }).bindPopup(popupHtml)
}

/** Pans/zooms the map to a quest layer and opens its popup. */
export function focusQuestLayer(map: L.Map, layer: L.Layer): void {
  if (layer instanceof L.CircleMarker) {
    map.setView(layer.getLatLng(), Math.max(map.getZoom(), 17))
  } else if (layer instanceof L.GeoJSON) {
    map.fitBounds(layer.getBounds(), { padding: [30, 30], maxZoom: 18 })
  }
  layer.openPopup()
}
