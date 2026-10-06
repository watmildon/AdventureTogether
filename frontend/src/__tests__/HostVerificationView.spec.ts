import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import HostVerificationView from '../views/HostVerificationView.vue'
import { createRouter, createMemoryHistory } from 'vue-router'

vi.mock('../api', async (importOriginal) => {
  const actual: any = await importOriginal()
  return {
    ...actual,
    api: {
      getEvent: vi.fn().mockResolvedValue({ id: 1, title: 'Demo', hashtag: 'Demo' }),
      getSubmissions: vi.fn().mockResolvedValue([]),
      getTeamProgress: vi.fn().mockResolvedValue([]),
      verifySubmission: vi.fn()
    }
  }
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    {
      path: '/events/:id/host/verify',
      name: 'host-verify',
      component: HostVerificationView
    }
  ]
})

describe('HostVerificationView Component', () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    // restoreAllMocks clears mock implementations, so re-apply the defaults
    const { api } = await import('../api')
    ;(api.getEvent as any).mockResolvedValue({ id: 1, title: 'Demo', hashtag: 'Demo' })
    ;(api.getSubmissions as any).mockResolvedValue([])
    ;(api.getTeamProgress as any).mockResolvedValue([])
  })

  it('renders the verification portal header and filter controls', async () => {
    router.push('/events/1/host/verify')
    await router.isReady()

    const wrapper = mount(HostVerificationView, {
      global: {
        plugins: [router]
      }
    })

    expect(wrapper.text()).toContain('Host Verification Portal')
    expect(wrapper.text()).toContain('Verification Status:')
    expect(wrapper.text()).toContain('Source Platform:')
  })

  it('shows new platforms with element counts, filters by platform and opens team progress', async () => {
    const { api } = await import('../api')
    ;(api.getSubmissions as any).mockResolvedValue([
      {
        id: 1, event: 1, quest: 18, quest_title: 'Alkali Flat', team: 4, team_name: 'Organisers',
        platform: 'ohm', platform_display: 'OpenHistoricalMap', external_id: '555', author_username: 'alice_osm',
        external_url: 'https://www.openhistoricalmap.org/changeset/555', diff_payload: {}, is_verified: false,
        verified_by_username: null, verified_at: null, element_count: 3, contributed_at: '2026-11-04T19:00:00Z', created_at: ''
      },
      {
        id: 2, event: 1, quest: 21, quest_title: 'Ship a patch', team: null, team_name: null,
        platform: 'github', platform_display: 'GitHub', external_id: 'OSGeo/gdal#1', author_username: 'alice-gh',
        external_url: 'https://github.com/OSGeo/gdal/pull/1', diff_payload: {}, is_verified: false,
        verified_by_username: null, verified_at: null, element_count: 1, contributed_at: null, created_at: ''
      }
    ])
    ;(api.getTeamProgress as any).mockResolvedValue([
      { quest: 18, quest_title: 'Alkali Flat', count: 3, target_count: 1, points_reward: 35, completed_at: '2026-11-04T19:05:00Z', points_awarded: true }
    ])

    router.push('/events/1/host/verify')
    await router.isReady()
    const wrapper = mount(HostVerificationView, { global: { plugins: [router] } })
    await flushPromises()

    const rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0].find('.platform-badge').text()).toContain('OpenHistoricalMap')
    expect(rows[0].text()).toContain('3 elements')
    expect(rows[0].find('.contributed-at').exists()).toBe(true)
    expect(rows[1].text()).toContain('1 element')
    expect(rows[1].find('.platform-badge').text()).toContain('GitHub')

    // Platform filter lists the new platforms
    const select = wrapper.findAll('select')[1]
    expect(select.findAll('option').map((o) => o.attributes('value'))).toEqual(
      expect.arrayContaining(['ohm', 'osm_notes', 'checkin', 'github', 'panoramax'])
    )
    await select.setValue('github')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    await select.setValue('all')

    // Team progress drawer
    await wrapper.find('.link-btn').trigger('click')
    await flushPromises()
    expect(api.getTeamProgress).toHaveBeenCalledWith(4)
    expect(wrapper.find('.progress-card').text()).toContain('Progress: Organisers')
    expect(wrapper.find('.progress-card').text()).toContain('3/1')
    expect(wrapper.find('.progress-card').text()).toContain('+35 pts')
  })
})
