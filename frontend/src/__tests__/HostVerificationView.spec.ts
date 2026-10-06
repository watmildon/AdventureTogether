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
      getQuests: vi.fn().mockResolvedValue([]),
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
    ;(api.getQuests as any).mockResolvedValue([])
  })

  it('shows the value on value-scoring submissions and saves a correction through verify', async () => {
    const { api } = await import('../api')
    const stamp = {
      id: 7, event: 1, quest: 24, quest_title: 'Stamped in Sacramento', team: 4, team_name: 'Organisers',
      platform: 'commons', platform_display: 'Wikimedia Commons', external_id: '501/q24', author_username: 'Photo Alice',
      external_url: 'https://commons.wikimedia.org/wiki/File:Stamp.jpg', diff_payload: { title: 'File:Stamp.jpg' },
      is_verified: false, verified_by_username: null, verified_at: null, element_count: 1, contributed_at: null,
      extracted_value: 1923, created_at: ''
    }
    ;(api.getSubmissions as any).mockResolvedValue([
      stamp,
      { ...stamp, id: 8, quest: 3, quest_title: 'Lock it up', platform: 'osm', external_id: '9/q3', extracted_value: null }
    ])
    ;(api.getQuests as any).mockResolvedValue([
      { id: 24, criteria_type: 'wikimedia_commons', validation_rules: { scoring: { value: { kind: 'year' }, per_bucket: { size: 10, points: 5 } } } },
      { id: 3, criteria_type: 'osm_tags', validation_rules: { target_count: 10 } }
    ])
    ;(api.verifySubmission as any).mockResolvedValue({ ...stamp, extracted_value: 1913, is_verified: false })

    router.push('/events/1/host/verify')
    await router.isReady()
    const wrapper = mount(HostVerificationView, { global: { plugins: [router] } })
    await flushPromises()

    const rows = wrapper.findAll('tbody tr')
    expect(rows[0].find('.value-cell').text()).toContain('Value: 1923')
    // Quests that do not score values get no value cell
    expect(rows[1].find('.value-cell').exists()).toBe(false)

    await rows[0].find('.value-edit').trigger('click')
    await rows[0].find('.value-input').setValue('1913')
    await rows[0].find('.value-save').trigger('click')
    await flushPromises()

    // The verification state is kept: only the value changes
    expect(api.verifySubmission).toHaveBeenCalledWith(7, 'Host', { isVerified: false, extractedValue: 1913 })
    expect(wrapper.findAll('tbody tr')[0].find('.value-cell').text()).toContain('Value: 1913')
    expect(wrapper.text()).toContain('Value for #501/q24 set to 1913.')
  })

  it('un-verifies a verified submission from the toggle', async () => {
    const { api } = await import('../api')
    const sub = {
      id: 9, event: 1, quest: 3, quest_title: 'Lock it up', team: null, team_name: null, platform: 'osm',
      external_id: '9/q3', author_username: 'a', external_url: 'https://www.openstreetmap.org/changeset/9',
      diff_payload: {}, is_verified: true, verified_by_username: 'Host', verified_at: '', created_at: ''
    }
    ;(api.getSubmissions as any).mockResolvedValue([sub])
    ;(api.verifySubmission as any).mockResolvedValue({ ...sub, is_verified: false, verified_by_username: null })

    router.push('/events/1/host/verify')
    await router.isReady()
    const wrapper = mount(HostVerificationView, { global: { plugins: [router] } })
    await flushPromises()
    await wrapper.find('tbody tr .btn-primary').trigger('click')
    await flushPromises()
    expect(api.verifySubmission).toHaveBeenCalledWith(9, 'Host', { isVerified: false })
    expect(wrapper.find('tbody tr').text()).toContain('Verify')
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
