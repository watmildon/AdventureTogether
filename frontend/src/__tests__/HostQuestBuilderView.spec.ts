import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import HostQuestBuilderView from '../views/HostQuestBuilderView.vue'

// Keep ApiError real (the view checks instanceof) and stub the network calls
vi.mock('../api', async (importOriginal) => {
  const actual: any = await importOriginal()
  return {
    ...actual,
    api: {
      getEvent: vi.fn(),
      getQuests: vi.fn(),
      getSessions: vi.fn(),
      createQuest: vi.fn(),
      deleteQuest: vi.fn()
    }
  }
})

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/events/:id/host/builder', component: HostQuestBuilderView }]
})

const sessions = [
  {
    code: 'OHM01',
    title: 'OpenHistoricalMap: across the geoverse',
    speakers: ['Minh Nguyễn'],
    start: '2026-11-04T11:00:00-08:00',
    room: 'Beavis',
    track: null,
    url: 'https://talks.osgeo.org/foss4g-na-2026/talk/OHM01/',
    type: 'Talk'
  },
  {
    code: 'GDAL01',
    title: 'Code is liability',
    speakers: ['Howard Butler'],
    start: '2026-11-03T11:00:00-08:00',
    room: 'Bondi',
    track: null,
    url: 'https://talks.osgeo.org/foss4g-na-2026/talk/GDAL01/',
    type: 'Talk'
  }
]

const mountBuilder = async () => {
  router.push('/events/2/host/builder')
  await router.isReady()
  // Not attached to the document, so the Leaflet map is skipped (no #builder-map element)
  const wrapper = mount(HostQuestBuilderView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('HostQuestBuilderView', () => {
  let api: any

  beforeEach(async () => {
    ;({ api } = await import('../api'))
    vi.clearAllMocks()
    api.getEvent.mockResolvedValue({ id: 2, title: 'FOSS4G NA 2026 Open Data Hunt', hashtag: 'FOSS4GNA2026', bounding_polygon: null })
    api.getQuests.mockResolvedValue([])
    api.getSessions.mockResolvedValue(sessions)
    api.createQuest.mockImplementation(async (payload: any) => ({ id: 99, is_active: true, ...payload }))
  })

  it('offers all nine quest types', async () => {
    const wrapper = await mountBuilder()
    expect(wrapper.findAll('#criteriaType option')).toHaveLength(9)
  })

  it('composes osm_tags rules from tag rows and target count', async () => {
    const wrapper = await mountBuilder()
    await wrapper.find('#questTitle').setValue('Farm-to-fork hours')
    await wrapper.find('#questDesc').setValue('Add opening_hours to 5 cafes.')

    const keys = wrapper.findAll('.tag-key')
    await keys[0].setValue('amenity')
    await wrapper.findAll('.tag-value')[0].setValue('cafe')
    await wrapper.find('.add-tag').trigger('click')
    await wrapper.findAll('.tag-key')[2].setValue('wheelchair')
    await wrapper.findAll('.tag-value')[2].setValue('')
    await wrapper.find('#targetCount').setValue(5)

    // Pick a session through the filter
    await wrapper.find('input[aria-label="Filter sessions"]').setValue('butler')
    const options = wrapper.findAll('.session-option')
    expect(options).toHaveLength(1)
    await options[0].trigger('click')

    await wrapper.find('.btn-primary.btn-block').trigger('click')
    await flushPromises()

    expect(api.createQuest).toHaveBeenCalledTimes(1)
    const payload = api.createQuest.mock.calls[0][0]
    expect(payload.criteria_type).toBe('osm_tags')
    // Whole event area: no point, so no radius_m
    expect(payload.target_geometry).toBeNull()
    expect(payload.validation_rules).toEqual({
      required_tags: { amenity: 'cafe', opening_hours: '*', wheelchair: '*' },
      target_count: 5,
      require_hashtag: true
    })
    // The session list's `type` is not part of inspired_by
    expect(payload.inspired_by).toEqual({
      code: 'GDAL01',
      title: 'Code is liability',
      speakers: ['Howard Butler'],
      start: '2026-11-03T11:00:00-08:00',
      room: 'Bondi',
      track: null,
      url: 'https://talks.osgeo.org/foss4g-na-2026/talk/GDAL01/'
    })
    expect(payload.is_active).toBe(true)
    expect(payload.window_start).toBeNull()
  })

  it('composes wikidata_statement rules and blocks saving without a valid item', async () => {
    const wrapper = await mountBuilder()
    await wrapper.find('#questTitle').setValue('Fill in the architect')
    await wrapper.find('#questDesc').setValue('Add P84 and P571.')
    await wrapper.find('#criteriaType').setValue('wikidata_statement')

    await wrapper.find('.btn-primary.btn-block').trigger('click')
    expect(wrapper.text()).toContain('Enter the Wikidata item id')
    expect(api.createQuest).not.toHaveBeenCalled()

    await wrapper.find('#wikidataQid').setValue('q111393295')
    await wrapper.find('#wikidataProperties').setValue('P84, p571')
    await wrapper.find('#targetCount').setValue(2)
    await wrapper.find('.btn-primary.btn-block').trigger('click')
    await flushPromises()

    expect(api.createQuest.mock.calls[0][0].validation_rules).toEqual({
      qid: 'Q111393295',
      properties: ['P84', 'P571'],
      target_count: 2
    })
    expect(api.createQuest.mock.calls[0][0].inspired_by).toEqual({})
  })

  it('saves street_imagery as inactive', async () => {
    const wrapper = await mountBuilder()
    await wrapper.find('#questTitle').setValue('Street view, open')
    await wrapper.find('#questDesc').setValue('Capture K St.')
    await wrapper.find('#criteriaType').setValue('street_imagery')
    expect(wrapper.text()).toContain('Coming soon')
    await wrapper.find('.btn-primary.btn-block').trigger('click')
    await flushPromises()
    expect(api.createQuest.mock.calls[0][0]).toMatchObject({ is_active: false, validation_rules: { target_count: 1 } })
  })

  it('explains a missing schedule and accepts a hand-entered session', async () => {
    const { ApiError } = await import('../api')
    api.getSessions.mockRejectedValue(new ApiError('This event has no schedule_url configured.', 400))
    const wrapper = await mountBuilder()
    expect(wrapper.text()).toContain('Set a schedule URL on the event to pick sessions')

    await wrapper.find('#questTitle').setValue('Icebreaker')
    await wrapper.find('#questDesc').setValue('Be there.')
    await wrapper.find('input[aria-label="Session title"]').setValue('Welcome Icebreaker BBQ')
    await wrapper.find('.btn-primary.btn-block').trigger('click')
    await flushPromises()
    expect(api.createQuest.mock.calls[0][0].inspired_by).toEqual({ title: 'Welcome Icebreaker BBQ' })
  })

  it('shows an error when the schedule cannot be fetched', async () => {
    const { ApiError } = await import('../api')
    api.getSessions.mockRejectedValue(new ApiError('bad gateway', 502))
    const wrapper = await mountBuilder()
    expect(wrapper.text()).toContain('could not be fetched')
  })

  it('deletes a quest after confirmation', async () => {
    api.getQuests.mockResolvedValue([
      { id: 5, title: 'Give the venue a face', criteria_type: 'wikimedia_commons', points_reward: 20, is_active: true }
    ])
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    const wrapper = await mountBuilder()
    expect(wrapper.find('.quest-item').text()).toContain('Commons')

    await wrapper.find('.delete-btn').trigger('click')
    expect(api.deleteQuest).not.toHaveBeenCalled()

    await wrapper.find('.delete-btn').trigger('click')
    await flushPromises()
    expect(api.deleteQuest).toHaveBeenCalledWith(5)
    expect(wrapper.findAll('.quest-item')).toHaveLength(0)
    confirmSpy.mockRestore()
  })
})
