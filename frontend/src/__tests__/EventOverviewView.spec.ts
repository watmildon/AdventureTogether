import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import EventOverviewView from '../views/backoffice/EventOverviewView.vue'

vi.mock('../api', async (importOriginal) => {
  const actual: any = await importOriginal()
  return {
    ...actual,
    api: {
      getLeaderboard: vi.fn(),
      countSubmissions: vi.fn(),
      countQuests: vi.fn(),
      triggerHarvest: vi.fn()
    }
  }
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/backoffice/events/:id', component: EventOverviewView }, { path: '/:rest(.*)*', component: { template: '<div />' } }]
})

describe('EventOverviewView', () => {
  beforeEach(async () => {
    const { api } = await import('../api')
    vi.mocked(api.getLeaderboard).mockResolvedValue([{ id: 1, name: 'Organisers (demo)', score: 10, member_count: 1, completed_quests: 1 }])
    vi.mocked(api.countSubmissions).mockResolvedValue(3)
    vi.mocked(api.countQuests).mockResolvedValue(22)
  })

  it('shows pending count, leaderboard and participant links, and polls with per-platform stats', async () => {
    const { api } = await import('../api')
    vi.mocked(api.triggerHarvest).mockResolvedValue({
      message: 'Harvest completed for event 2.',
      stats: { event: 2, found: true, dry_run: false, summary: {}, warnings: ['commons: timeout'], osm: { harvested: 4, created: 2, updated: 0, matched: 2, errors: 0 }, commons: { harvested: 0, errors: 1 } }
    })
    router.push('/backoffice/events/2')
    await router.isReady()
    const wrapper = mount(EventOverviewView, { global: { plugins: [router] } })
    await flushPromises()

    expect(api.countSubmissions).toHaveBeenCalledWith('2', false)
    expect(wrapper.find('[data-testid="pending-count"]').text()).toBe('3')
    expect(wrapper.text()).toContain('Organisers (demo)')
    expect(wrapper.text()).toContain('/events/2/map')

    await wrapper.find('.harvest-card button').trigger('click')
    await flushPromises()
    expect(api.triggerHarvest).toHaveBeenCalledWith('2')
    const osm = wrapper.find('tr[data-platform="osm"]')
    expect(osm.text()).toContain('OpenStreetMap')
    expect(osm.findAll('td').map((td) => td.text()).slice(1)).toEqual(['4', '2', '0', '2', '0'])
    expect(wrapper.find('tr[data-platform="commons"] .bad').text()).toBe('1')
    expect(wrapper.text()).toContain('commons: timeout')
    // Counts refresh after polling
    expect(api.countSubmissions).toHaveBeenCalledTimes(2)
  })

  it('shows the error when the harvest is refused (inactive event)', async () => {
    const { api, ApiError } = await import('../api')
    vi.mocked(api.triggerHarvest).mockRejectedValue(new ApiError('Event 2 not found or inactive.', 404))
    router.push('/backoffice/events/2')
    await router.isReady()
    const wrapper = mount(EventOverviewView, { global: { plugins: [router] } })
    await flushPromises()
    await wrapper.find('.harvest-card button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('inactive')
  })
})
