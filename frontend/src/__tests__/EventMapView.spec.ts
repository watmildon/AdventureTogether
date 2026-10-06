import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import EventMapView from '../views/EventMapView.vue'
import type { QuestData } from '../api'

vi.mock('../api', async (importOriginal) => {
  const actual: any = await importOriginal()
  return {
    ...actual,
    api: {
      getEvent: vi.fn(),
      getQuests: vi.fn(),
      getActiveLocations: vi.fn(),
      getCheckins: vi.fn(),
      getLeaderboard: vi.fn(),
      getTeamProgress: vi.fn(),
      getQuestTargets: vi.fn(),
      pingLocation: vi.fn()
    }
  }
})

// jsdom has neither SVG nor canvas, so Leaflet vector layers (the "you are here" marker)
// cannot be added. Swap them for inert stand-ins; the rest of Leaflet runs for real.
vi.mock('leaflet', async (importOriginal) => {
  const actual: any = await importOriginal()
  const L = actual.default ?? actual
  const inertLayer = () => {
    const layer: any = {}
    for (const method of ['addTo', 'bindPopup', 'setLatLng', 'setRadius', 'openPopup', 'remove']) layer[method] = () => layer
    return layer
  }
  const patched = { ...L, circle: inertLayer, circleMarker: inertLayer }
  return { ...actual, ...patched, default: patched }
})

// The target markers are Leaflet vectors too; hand back a stand-in so their add/remove can be seen
const targetsLayer = { addTo: vi.fn() }
vi.mock('../composables/questLayers', async (importOriginal) => {
  const actual: any = await importOriginal()
  return { ...actual, createWikidataTargetsLayer: vi.fn(() => targetsLayer) }
})

const quest = (id: number, title: string, minMinutes = 0): QuestData => ({
  id,
  event: 2,
  title,
  description: '',
  target_geometry: null,
  criteria_type: 'location_checkin',
  validation_rules: { radius_m: 50, min_minutes: minMinutes },
  points_reward: 10,
  is_active: true,
  created_at: ''
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/events/:id/map', component: EventMapView },
    { path: '/events/:id/join', component: { template: '<div />' } }
  ]
})

let wrapper: VueWrapper | null = null

const mountMap = async (eventId: number) => {
  router.push(`/events/${eventId}/map`)
  await router.isReady()
  wrapper = mount(EventMapView, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('EventMapView', () => {
  beforeEach(async () => {
    localStorage.clear()
    const { api } = await import('../api')
    vi.mocked(api.getEvent).mockResolvedValue({ id: 2, title: 'FOSS4G NA', hashtag: 'foss4gna' } as any)
    vi.mocked(api.getQuests).mockResolvedValue([
      quest(11, 'Capitol check-in'),
      quest(12, 'Dwell quest', 10),
      quest(13, 'Revoked quest'),
      quest(14, 'Instant pending')
    ])
    vi.mocked(api.getActiveLocations).mockResolvedValue([])
    vi.mocked(api.getCheckins).mockResolvedValue([])
    vi.mocked(api.getLeaderboard).mockResolvedValue([])
    vi.mocked(api.getTeamProgress).mockResolvedValue([])
    vi.mocked(api.pingLocation).mockReset()
    vi.mocked(api.getTeamProgress).mockClear()
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
  })

  it('does not use a team joined for another event', async () => {
    const { api } = await import('../api')
    // Joined team 4 on event 1; the global keys point at it too
    localStorage.setItem('team_for_event_1', JSON.stringify({ id: 4, name: 'Organisers' }))
    localStorage.setItem('team_id', '4')
    localStorage.setItem('team_name', 'Organisers')

    const view = await mountMap(2)

    expect(view.text()).toContain('Join a team')
    expect(view.text()).not.toContain('Organisers')
    expect(api.getTeamProgress).not.toHaveBeenCalled()
  })

  it("uses this event's stored team", async () => {
    const { api } = await import('../api')
    localStorage.setItem('team_for_event_2', JSON.stringify({ id: 7, name: 'Mappers' }))

    const view = await mountMap(2)

    expect(view.text()).toContain('Progress for Mappers')
    expect(api.getTeamProgress).toHaveBeenCalledWith(7)
  })

  it("takes the team and check-in state from this event's ping response", async () => {
    const { api } = await import('../api')
    localStorage.setItem('simulated_gps', JSON.stringify({ lat: 38.57664, lng: -121.4936 }))
    localStorage.setItem('team_id', '4')
    vi.mocked(api.pingLocation).mockResolvedValue({
      id: 1, event: 2, user_identifier: 'me', display_name: 'Me', team: 9, team_name: 'Ping Team',
      longitude: -121.4936, latitude: 38.57664, visibility: 'team', is_foreground: true, recorded_at: '',
      checkins: [{ quest: 11, quest_title: 'Capitol check-in', status: 'verified' }]
    })

    const view = await mountMap(2)

    expect(api.pingLocation).toHaveBeenCalled()
    expect(view.text()).toContain('Progress for Ping Team')
    expect(api.getTeamProgress).toHaveBeenCalledWith(9)
    expect(view.find('.quest-card[data-quest-id="11"]').text()).toContain('✓ Checked in')
  })

  it('restores check-in state on reload from the status field', async () => {
    const { api } = await import('../api')
    vi.mocked(api.getCheckins).mockResolvedValue([
      { quest: 11, quest_title: 'Capitol check-in', status: 'verified', min_minutes: 0 },
      { quest: 12, quest_title: 'Dwell quest', status: 'pending', min_minutes: 10 },
      { quest: 13, quest_title: 'Revoked quest', status: 'revoked', min_minutes: 0 },
      { quest: 14, quest_title: 'Instant pending', status: 'pending', min_minutes: 0 }
    ])

    const view = await mountMap(2)
    const card = (id: number) => view.find(`.quest-card[data-quest-id="${id}"]`).text()

    expect(card(11)).toContain('✓ Checked in')
    expect(card(12)).toContain("You're here, stay a few minutes")
    expect(card(12)).not.toContain('Checked in')
    expect(card(13)).not.toContain('Checked in')
    expect(card(13)).not.toContain("You're here")
    expect(card(14)).toContain("You're here")
    expect(card(14)).not.toContain('Checked in')
  })

  it('fetches wikidata_area targets on the first toggle only', async () => {
    const { api } = await import('../api')
    vi.mocked(api.getQuests).mockResolvedValue([
      { ...quest(30, 'Picture this'), criteria_type: 'wikidata_area', validation_rules: { properties: ['P18'] } }
    ])
    vi.mocked(api.getQuestTargets).mockResolvedValue({ quest: 30, count: 113, targets: [] })

    const view = await mountMap(2)
    const card = () => view.find('.quest-card[data-quest-id="30"]')
    expect(api.getQuestTargets).not.toHaveBeenCalled()

    await card().find('.targets-btn').trigger('click')
    await flushPromises()
    expect(api.getQuestTargets).toHaveBeenCalledWith(30)
    expect(targetsLayer.addTo).toHaveBeenCalledTimes(1)
    expect(card().find('.targets-text').text()).toBe('113 nearby items need a photo')
    expect(card().find('.targets-btn').text()).toBe('Hide from map')

    await card().find('.targets-btn').trigger('click')
    await card().find('.targets-btn').trigger('click')
    await flushPromises()
    expect(api.getQuestTargets).toHaveBeenCalledTimes(1)
    expect(targetsLayer.addTo).toHaveBeenCalledTimes(2)
    expect(card().find('.targets-btn').text()).toBe('Hide from map')
  })

  it('links to WikiShootMe at the participant position', async () => {
    localStorage.setItem('simulated_gps', JSON.stringify({ lat: 38.579, lng: -121.4899 }))
    vi.mocked((await import('../api')).api.pingLocation).mockResolvedValue({} as any)
    const view = await mountMap(2)
    const link = view.find('a.wikishootme-link')
    expect(link.attributes('href')).toBe('https://wikishootme.toolforge.org/#lat=38.579000&lng=-121.489900&zoom=17')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.text()).toContain('Open WikiShootMe here')
  })
})
