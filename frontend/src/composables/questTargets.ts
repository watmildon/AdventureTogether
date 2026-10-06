/**
 * The "items that still need a photo" line of wikidata_area quest cards (the markers themselves
 * are drawn by questLayers.createWikidataTargetsLayer). EventMapView fetches the targets lazily
 * (GET /quests/<id>/targets/) the first time the participant asks to see them, and keeps one
 * TargetsState per quest. Kept free of Vue and Leaflet so it can be unit-tested directly.
 */

import type { QuestData } from '../api'

export interface TargetsState {
  status: 'loading' | 'loaded' | 'error'
  /** Number of target items once loaded. */
  count: number
  /** Whether the target markers are on the map. */
  shown: boolean
}

/** The quest's property ids, as the backend reads them (P18 when none are set). */
export function areaProperties(quest: Pick<QuestData, 'validation_rules'>): string[] {
  const raw = quest.validation_rules?.properties
  const list = Array.isArray(raw) ? raw : typeof raw === 'string' ? raw.split(/[\s,]+/) : []
  const props = list.map((p) => String(p).trim().toUpperCase()).filter((p) => /^P\d+$/.test(p))
  return props.length ? props : ['P18']
}

/** "113 nearby items need a photo" (P18 only), or "4 nearby items still lack P373" otherwise. */
export function targetsSummary(count: number, properties: string[]): string {
  const items = `${count} nearby item${count === 1 ? '' : 's'}`
  if (properties.length === 1 && properties[0] === 'P18') return `${items} ${count === 1 ? 'needs' : 'need'} a photo`
  return `${items} still lack ${properties.join(' / ')}`
}

/** What the card shows for the quest's targets: the line, the toggle label, and whether it is busy. */
export function targetsCardLine(
  state: TargetsState | undefined,
  properties: string[]
): { text: string; button: string; busy: boolean } {
  const what = properties.length === 1 && properties[0] === 'P18' ? 'need a photo' : `lack ${properties.join(' / ')}`
  if (!state) return { text: `Nearby items that ${what}`, button: 'Show on map', busy: false }
  if (state.status === 'loading') return { text: 'Finding nearby items…', button: 'Show on map', busy: true }
  if (state.status === 'error') return { text: 'Could not load nearby items', button: 'Retry', busy: false }
  return { text: targetsSummary(state.count, properties), button: state.shown ? 'Hide from map' : 'Show on map', busy: false }
}
