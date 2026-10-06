import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import BackofficeEventsView from '../views/backoffice/BackofficeEventsView.vue'

vi.mock('../api', async (importOriginal) => {
  const actual: any = await importOriginal()
  return {
    ...actual,
    api: {
      getEvents: vi.fn(),
      countQuests: vi.fn(),
      countTeams: vi.fn()
    }
  }
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/backoffice', component: BackofficeEventsView },
    { path: '/backoffice/:rest(.*)*', component: { template: '<div />' } }
  ]
})

describe('BackofficeEventsView', () => {
  beforeEach(async () => {
    const { api } = await import('../api')
    vi.mocked(api.getEvents).mockResolvedValue([
      { id: 1, title: 'SF demo', hashtag: 'SFDemo', is_active: true, start_time: '2020-01-01T00:00:00Z', end_time: '2099-01-01T00:00:00Z' },
      { id: 2, title: 'FOSS4G NA', hashtag: 'FOSS4GNA2026', is_active: true, start_time: '2098-11-02T16:00:00Z', end_time: '2098-11-05T02:00:00Z' },
      { id: 3, title: 'Old hunt', hashtag: 'Old', is_active: false, start_time: '2019-01-01T00:00:00Z', end_time: '2019-01-02T00:00:00Z' }
    ] as any)
    vi.mocked(api.countQuests).mockImplementation(async (id) => (id === 2 ? 22 : 3))
    vi.mocked(api.countTeams).mockImplementation(async (id) => {
      if (id === 3) throw new Error('boom')
      return id === 2 ? 1 : 4
    })
  })

  it('lists all events, newest first, with status, hashtag, counts and links', async () => {
    router.push('/backoffice')
    await router.isReady()
    const wrapper = mount(BackofficeEventsView, { global: { plugins: [router] } })
    await flushPromises()

    const rows = wrapper.findAll('.event-row')
    expect(rows.map((r) => r.attributes('data-event-id'))).toEqual(['2', '1', '3'])

    expect(rows[0].text()).toContain('Upcoming')
    expect(rows[0].text()).toContain('#FOSS4GNA2026')
    expect(rows[0].text()).toContain('22 quests')
    expect(rows[0].text()).toContain('1 team')
    expect(rows[1].text()).toContain('Live')
    expect(rows[2].text()).toContain('Inactive')
    // A failed count shows a dash instead of breaking the row
    expect(rows[2].text()).toContain('– teams')

    expect(rows[0].find('a.btn-primary').attributes('href')).toBe('/backoffice/events/2')
    expect(rows[0].find('a.btn-outline').attributes('href')).toBe('/backoffice/events/2/edit')
    expect(wrapper.find('.page-header a').attributes('href')).toBe('/backoffice/events/new')
  })
})
