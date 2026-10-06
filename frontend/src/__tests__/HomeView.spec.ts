import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import QuestPanel from '../components/QuestPanel.vue'
import { readTools } from '../composables/participantProfile'
import type { QuestData } from '../api'

vi.mock('../api', async (importOriginal) => {
  const actual: any = await importOriginal()
  return {
    ...actual,
    api: {
      getEvents: vi.fn(),
      getLeaderboard: vi.fn()
    }
  }
})

const event = (id: number, overrides: Record<string, any> = {}) => ({
  id,
  title: `Event ${id}`,
  slug: `event-${id}`,
  description: '',
  hashtag: `Tag${id}`,
  bounding_polygon: null,
  start_time: '2026-01-01T00:00:00Z',
  end_time: '2099-01-01T00:00:00Z',
  schedule_url: '',
  is_active: true,
  created_at: '',
  ...overrides
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: HomeView },
    { path: '/events/:id/map', component: { template: '<div />' } },
    { path: '/events/:id/join', component: { template: '<div />' } },
    { path: '/backoffice', component: { template: '<div />' } }
  ]
})

const mountHome = async () => {
  router.push('/')
  await router.isReady()
  const wrapper = mount(HomeView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('HomeView (participant landing page)', () => {
  beforeEach(async () => {
    localStorage.clear()
    const { api } = await import('../api')
    vi.mocked(api.getEvents).mockResolvedValue([event(1), event(2)] as any)
    vi.mocked(api.getLeaderboard).mockResolvedValue([])
  })

  it('shows the sections in order: profile, tools, events, then the back office link', async () => {
    const wrapper = await mountHome()
    const headings = wrapper.findAll('h2').map((h) => h.text())
    expect(headings).toEqual(['Your profile', 'Tools I have', 'Your events and teams'])
    expect(wrapper.find('.home-footer a').attributes('href')).toBe('/backoffice')
  })

  it('generates a participant id once and persists the profile as it is typed', async () => {
    const wrapper = await mountHome()
    const id = localStorage.getItem('participant_id')
    expect(id).toMatch(/^user-/)

    await wrapper.find('#profileName').setValue('Alex')
    await wrapper.find('#profileOsm').setValue(' alex_osm ')
    await wrapper.find('#profileGithub').setValue('alex-gh')
    await wrapper.find('input[name="profileVisibility"][value="quest"]').setValue(true)
    await flushPromises()

    expect(localStorage.getItem('participant_name')).toBe('Alex')
    expect(localStorage.getItem('participant_osm_username')).toBe('alex_osm')
    expect(localStorage.getItem('participant_github_username')).toBe('alex-gh')
    expect(localStorage.getItem('participant_wikimedia_username')).toBeNull()
    expect(localStorage.getItem('privacy_visibility')).toBe('quest')
    expect(wrapper.text()).toContain('So your edits are credited to your team.')

    // Clearing a username removes its key; the id is not regenerated on a second visit
    await wrapper.find('#profileOsm').setValue('')
    await flushPromises()
    expect(localStorage.getItem('participant_osm_username')).toBeNull()
    wrapper.unmount()
    await mountHome()
    expect(localStorage.getItem('participant_id')).toBe(id)
  })

  it('prefills the profile from storage', async () => {
    localStorage.setItem('participant_name', 'Sam')
    localStorage.setItem('participant_wikimedia_username', 'SamW')
    localStorage.setItem('privacy_visibility', 'nobody')
    const wrapper = await mountHome()
    expect((wrapper.find('#profileName').element as HTMLInputElement).value).toBe('Sam')
    expect((wrapper.find('#profileWikimedia').element as HTMLInputElement).value).toBe('SamW')
    expect((wrapper.find('input[value="nobody"]').element as HTMLInputElement).checked).toBe(true)
  })

  it('saves ticked tools to participant_tools', async () => {
    const wrapper = await mountHome()
    // One per TOOLS entry, including Mangrove and MapRoulette
    expect(wrapper.findAll('.tool')).toHaveLength(11)
    await wrapper.find('input[data-tool="everydoor"]').setValue(true)
    await wrapper.find('input[data-tool="wikidata"]').setValue(true)
    await flushPromises()
    expect(JSON.parse(localStorage.getItem('participant_tools')!)).toEqual(['everydoor', 'wikidata'])
    expect(readTools()).toEqual(['everydoor', 'wikidata'])

    await wrapper.find('input[data-tool="everydoor"]').setValue(false)
    await flushPromises()
    expect(readTools()).toEqual(['wikidata'])
  })

  it('shows the joined team with its join code, or a join button', async () => {
    localStorage.setItem('team_for_event_2', JSON.stringify({ id: 9, name: 'Organisers (demo)', join_code: 'MDPZVH' }))
    const wrapper = await mountHome()
    const card1 = wrapper.find('[data-event-id="1"]')
    const card2 = wrapper.find('[data-event-id="2"]')

    expect(card1.find('.team-box').exists()).toBe(false)
    expect(card1.text()).toContain('Join or create a team')

    expect(card2.find('.team-box').text()).toContain('Organisers (demo)')
    expect(card2.find('.team-box code').text()).toBe('MDPZVH')
    expect(card2.find('.change-team').attributes('href')).toBe('/events/2/join')
    expect(card2.text()).not.toContain('Join or create a team')
    expect(card2.find('a.btn-primary').attributes('href')).toBe('/events/2/map')
  })

  it('lists only active events that have not ended', async () => {
    const { api } = await import('../api')
    vi.mocked(api.getEvents).mockResolvedValue([
      event(1),
      event(3, { is_active: false }),
      event(4, { end_time: '2020-01-01T00:00:00Z' }),
      event(5, { start_time: '2099-01-01T00:00:00Z', end_time: '2099-01-02T00:00:00Z' })
    ] as any)
    const wrapper = await mountHome()
    expect(wrapper.findAll('.event-card').map((c) => c.attributes('data-event-id'))).toEqual(['1', '5'])
  })
})

describe('Tools filter in the quest panel', () => {
  const quest = (id: number, criteria_type: QuestData['criteria_type']): QuestData => ({
    id, event: 2, title: `Quest ${id}`, description: '', target_geometry: null, criteria_type,
    validation_rules: {}, points_reward: 10, is_active: true, created_at: ''
  })
  const quests = [quest(1, 'osm_tags'), quest(2, 'wikimedia_commons'), quest(3, 'location_checkin'), quest(4, 'ohm_feature')]
  const ids = (wrapper: any) => wrapper.findAll('.quest-card').map((c: any) => Number(c.attributes('data-quest-id')))

  it('defaults to only doable quests once tools are ticked; check-ins always show', async () => {
    const wrapper = mount(QuestPanel, { props: { quests, tools: ['everydoor'] } })
    const toggle = wrapper.find('.doable-toggle input')
    expect((toggle.element as HTMLInputElement).checked).toBe(true)
    expect(ids(wrapper)).toEqual([1, 3])
    expect(wrapper.text()).toContain('2 quests hidden')

    // Off: everything shows, with a muted "Needs" line on the ones the tools cannot do
    await toggle.setValue(false)
    expect(ids(wrapper)).toEqual([1, 2, 3, 4])
    const commons = wrapper.find('.quest-card[data-quest-id="2"]')
    expect(commons.classes()).toContain('not-doable')
    expect(commons.find('.needs').text()).toBe('Needs: Wikimedia Commons or WikiShootMe (web)')
    expect(wrapper.find('.quest-card[data-quest-id="1"] .needs').exists()).toBe(false)
    expect(wrapper.find('.quest-card[data-quest-id="3"] .needs').exists()).toBe(false)
  })

  it('defaults to showing everything when no tools are ticked', () => {
    const wrapper = mount(QuestPanel, { props: { quests } })
    expect((wrapper.find('.doable-toggle input').element as HTMLInputElement).checked).toBe(false)
    expect(ids(wrapper)).toEqual([1, 2, 3, 4])
    expect(wrapper.find('.quest-card[data-quest-id="1"] .needs').text()).toBe(
      'Needs: StreetComplete, EveryDoor or OpenStreetMap web editor (iD)'
    )
    expect(wrapper.text()).toContain('Tick the tools you have')
  })
})
