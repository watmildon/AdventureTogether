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
      updateQuest: vi.fn(),
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

  it('adds action to osm_tags rules when "Counts" is not "Any edit"', async () => {
    const wrapper = await mountBuilder()
    const options = wrapper.findAll('#osmAction option')
    expect(options.map((option) => option.text())).toEqual([
      'Any edit (added or updated)',
      'Newly created only',
      'Updates to existing only'
    ])
    expect((wrapper.find('#osmAction').element as HTMLSelectElement).value).toBe('any')

    await wrapper.find('#questTitle').setValue('Emergency ready')
    await wrapper.find('#questDesc').setValue('Add hydrants and AEDs.')
    await wrapper.findAll('.tag-key')[0].setValue('emergency')
    await wrapper.findAll('.tag-value')[0].setValue('fire_hydrant|defibrillator')
    await wrapper.findAll('.btn-icon')[1].trigger('click')
    await wrapper.find('#osmAction').setValue('create')
    await wrapper.find('#targetCount').setValue(3)
    await wrapper.find('.btn-primary.btn-block').trigger('click')
    await flushPromises()

    expect(api.createQuest.mock.calls[0][0].validation_rules).toEqual({
      required_tags: { emergency: 'fire_hydrant|defibrillator' },
      target_count: 3,
      require_hashtag: true,
      action: 'create'
    })
  })

  it('hides the Counts select for other quest types', async () => {
    const wrapper = await mountBuilder()
    await wrapper.find('#criteriaType').setValue('ohm_feature')
    expect(wrapper.find('#osmAction').exists()).toBe(false)
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

  it('composes a value-scoring block (the sidewalk stamp quest)', async () => {
    const wrapper = await mountBuilder()
    await wrapper.find('#questTitle').setValue('Stamped in Sacramento')
    await wrapper.find('#questDesc').setValue('Photograph sidewalk contractor stamps.')
    await wrapper.find('#criteriaType').setValue('wikimedia_commons')
    await wrapper.find('#wikiCategory').setValue('Sidewalk contractor stamps in Sacramento, California')

    expect(wrapper.find('.scoring-section summary').text()).toContain('Value scoring')
    expect(wrapper.find('.scoring-section').text()).toContain('+5 for each distinct decade')
    expect(wrapper.find('#scoringSource').exists()).toBe(false)
    await wrapper.find('#scoringEnabled').setValue(true)

    // A default pattern follows the kind
    const pattern = () => (wrapper.find('#scoringPattern').element as HTMLInputElement).value
    const yearDefault = pattern()
    await wrapper.find('#scoringKind').setValue('number')
    expect(pattern()).toBe('-?\\d+(?:\\.\\d+)?')
    await wrapper.find('#scoringKind').setValue('year')
    expect(pattern()).toBe(yearDefault)
    await wrapper.find('#scoringPattern').setValue('\\b((?:18|19|20)\\d{2})\\b')

    await wrapper.find('.btn-primary.btn-block').trigger('click')
    await flushPromises()
    expect(api.createQuest.mock.calls[0][0].validation_rules).toEqual({
      category: 'Sidewalk contractor stamps in Sacramento, California',
      target_count: 1,
      scoring: {
        value: { source: 'description', pattern: '\\b((?:18|19|20)\\d{2})\\b', kind: 'year' },
        per_bucket: { size: 10, points: 5 },
        extreme_bonus: { direction: 'min', points: 25 }
      }
    })
  })

  it('asks for a tag key when value scoring reads a tag', async () => {
    const wrapper = await mountBuilder()
    await wrapper.find('#questTitle').setValue('Dated buildings')
    await wrapper.find('#questDesc').setValue('Add start_date.')
    await wrapper.find('#scoringEnabled').setValue(true)
    await wrapper.find('#scoringSource').setValue('tag')
    await wrapper.find('#scoringTag').setValue('')
    await wrapper.find('.btn-primary.btn-block').trigger('click')
    expect(wrapper.text()).toContain('Value scoring: enter the OSM tag to read')
    expect(api.createQuest).not.toHaveBeenCalled()
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

  describe('editing existing quests', () => {
    const lockItUp = {
      id: 11,
      event: 2,
      title: 'Lock it up',
      description: 'Map bike parking with capacity.',
      criteria_type: 'osm_tags',
      validation_rules: { required_tags: { amenity: 'bicycle_parking', capacity: '*' }, target_count: 10, require_hashtag: true },
      target_geometry: null,
      points_reward: 30,
      is_active: true,
      inspired_by: sessions[1],
      window_start: '2026-11-03T18:00:00Z',
      window_end: null,
      created_at: '2026-10-01T00:00:00Z'
    }
    const kerbs = {
      id: 10,
      event: 2,
      title: 'Every kerb counts',
      description: 'Tag crossings.',
      criteria_type: 'osm_tags',
      validation_rules: { required_tags: { highway: 'crossing', kerb: '*' }, target_count: 5, require_hashtag: true, note: 'keep me' },
      target_geometry: { type: 'Polygon', coordinates: [[[-121.5, 38.57], [-121.49, 38.57], [-121.49, 38.58], [-121.5, 38.57]]] },
      points_reward: 40,
      is_active: true,
      inspired_by: {},
      window_start: null,
      window_end: null,
      created_at: '2026-10-01T00:00:00Z'
    }
    const venue = {
      ...kerbs,
      id: 5,
      title: 'Give the venue a face',
      criteria_type: 'wikimedia_commons',
      validation_rules: { category: 'Sacramento', target_count: 2 },
      target_geometry: { type: 'Point', coordinates: [-121.49, 38.575] }
    }

    beforeEach(() => {
      api.getQuests.mockResolvedValue([lockItUp, kerbs, venue].map((q) => structuredClone(q)))
      api.updateQuest.mockImplementation(async (id: number, changes: any) => ({ ...kerbs, ...lockItUp, id, ...changes }))
    })

    const editButton = (wrapper: any, title: string) =>
      wrapper.findAll('.quest-item').find((item: any) => item.text().includes(title))!.find('.edit-btn')

    it('loads and changes the osm_tags action', async () => {
      api.getQuests.mockResolvedValue([{ ...structuredClone(lockItUp), validation_rules: { ...lockItUp.validation_rules, action: 'create' } }])
      const wrapper = await mountBuilder()
      await editButton(wrapper, 'Lock it up').trigger('click')
      expect((wrapper.find('#osmAction').element as HTMLSelectElement).value).toBe('create')

      await wrapper.find('#osmAction').setValue('any')
      await wrapper.find('.save-btn').trigger('click')
      await flushPromises()
      expect(api.updateQuest.mock.calls[0][1].validation_rules).toEqual({
        required_tags: { amenity: 'bicycle_parking', capacity: '*' },
        target_count: 10,
        require_hashtag: true
      })
    })

    it('populates the form from the quest', async () => {
      const wrapper = await mountBuilder()
      await editButton(wrapper, 'Lock it up').trigger('click')

      expect(wrapper.find('.form-heading').text()).toBe('Edit quest: Lock it up')
      expect((wrapper.find('#questTitle').element as HTMLInputElement).value).toBe('Lock it up')
      expect((wrapper.find('#questDesc').element as HTMLTextAreaElement).value).toBe('Map bike parking with capacity.')
      expect((wrapper.find('#criteriaType').element as HTMLSelectElement).value).toBe('osm_tags')
      expect(wrapper.findAll('.tag-key').map((input) => (input.element as HTMLInputElement).value)).toEqual(['amenity', 'capacity'])
      expect(wrapper.findAll('.tag-value').map((input) => (input.element as HTMLInputElement).value)).toEqual(['bicycle_parking', '*'])
      expect((wrapper.find('#targetCount').element as HTMLInputElement).value).toBe('10')
      expect((wrapper.find('#pointsReward').element as HTMLInputElement).value).toBe('30')
      expect((wrapper.find('#isActive').element as HTMLInputElement).checked).toBe(true)
      // datetime-local in the browser's time zone
      const start = new Date('2026-11-03T18:00:00Z')
      const pad = (n: number) => String(n).padStart(2, '0')
      const local = `${start.getFullYear()}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}T${pad(start.getHours())}:${pad(start.getMinutes())}`
      const windowInputs = wrapper.findAll('input[type="datetime-local"]')
      expect((windowInputs[0].element as HTMLInputElement).value).toBe(local)
      expect((windowInputs[1].element as HTMLInputElement).value).toBe('')
      expect(wrapper.find('.chosen-session').text()).toContain('Code is liability')
      expect(wrapper.text()).toContain('Whole event area')
      expect(wrapper.find('.quest-item.is-editing').text()).toContain('Lock it up')
      expect(wrapper.find('.save-btn').text()).toBe('Save changes')
    })

    it('saves a PATCH with composed rules and leaves a polygon target untouched', async () => {
      const wrapper = await mountBuilder()
      await editButton(wrapper, 'Every kerb counts').trigger('click')
      expect(wrapper.text()).toContain('Area target (polygon) set from the seed file, kept as is')

      await wrapper.find('#targetCount').setValue(7)
      await wrapper.find('#pointsReward').setValue(45)
      await wrapper.find('#isActive').setValue(false)
      await wrapper.find('.save-btn').trigger('click')
      await flushPromises()

      expect(api.createQuest).not.toHaveBeenCalled()
      expect(api.updateQuest).toHaveBeenCalledTimes(1)
      const [id, changes] = api.updateQuest.mock.calls[0]
      expect(id).toBe(10)
      expect(changes).not.toHaveProperty('target_geometry')
      expect(changes).toMatchObject({
        title: 'Every kerb counts',
        criteria_type: 'osm_tags',
        points_reward: 45,
        is_active: false,
        inspired_by: {},
        window_start: null,
        window_end: null
      })
      // Composed from the form; keys the form does not model are kept; no radius without a point
      expect(changes.validation_rules).toEqual({
        required_tags: { highway: 'crossing', kerb: '*' },
        target_count: 7,
        require_hashtag: true,
        note: 'keep me'
      })

      // Back in create mode, with the list updated in place
      expect(wrapper.find('.form-heading').text()).toBe('New quest')
      expect(wrapper.text()).toContain('Quest "Every kerb counts" saved.')
      const item = wrapper.findAll('.quest-item').find((li) => li.text().includes('Every kerb counts'))!
      expect(item.text()).toContain('45 pts')
      expect(item.text()).toContain('inactive')
    })

    it('sends a point target and re-initialises only the rules when the type changes', async () => {
      const wrapper = await mountBuilder()
      await editButton(wrapper, 'Give the venue a face').trigger('click')
      expect((wrapper.find('#wikiCategory').element as HTMLInputElement).value).toBe('Sacramento')
      expect(wrapper.text()).toContain('38.5750, -121.4900')

      await wrapper.find('#criteriaType').setValue('osm_notes')
      expect((wrapper.find('#targetCount').element as HTMLInputElement).value).toBe('1')
      expect((wrapper.find('#questTitle').element as HTMLInputElement).value).toBe('Give the venue a face')
      await wrapper.find('.save-btn').trigger('click')
      await flushPromises()

      const [, changes] = api.updateQuest.mock.calls[0]
      expect(changes.criteria_type).toBe('osm_notes')
      expect(changes.validation_rules).toEqual({ target_count: 1 })
      expect(changes.target_geometry).toEqual({ type: 'Point', coordinates: [-121.49, 38.575] })
    })

    it('loads value scoring and drops it when switched off', async () => {
      const scoring = { value: { source: 'description', kind: 'year' }, extreme_bonus: { direction: 'min', points: 25 } }
      api.getQuests.mockResolvedValue([{ ...structuredClone(venue), validation_rules: { ...venue.validation_rules, scoring } }])
      const wrapper = await mountBuilder()
      await editButton(wrapper, 'Give the venue a face').trigger('click')
      expect((wrapper.find('#scoringEnabled').element as HTMLInputElement).checked).toBe(true)
      expect((wrapper.find('#scoringBucket').element as HTMLInputElement).checked).toBe(false)
      expect((wrapper.find('#scoringBonusPoints').element as HTMLInputElement).value).toBe('25')

      await wrapper.find('#scoringEnabled').setValue(false)
      await wrapper.find('.save-btn').trigger('click')
      await flushPromises()
      expect(api.updateQuest.mock.calls[0][1].validation_rules).toEqual({ category: 'Sacramento', target_count: 2 })
    })

    it('cancel restores the empty create form', async () => {
      const wrapper = await mountBuilder()
      await editButton(wrapper, 'Give the venue a face').trigger('click')
      await wrapper.find('.cancel-btn').trigger('click')

      expect(wrapper.find('.form-heading').text()).toBe('New quest')
      expect((wrapper.find('#questTitle').element as HTMLInputElement).value).toBe('')
      expect((wrapper.find('#criteriaType').element as HTMLSelectElement).value).toBe('osm_tags')
      expect((wrapper.find('#pointsReward').element as HTMLInputElement).value).toBe('10')
      expect(wrapper.text()).toContain('Whole event area')
      expect(wrapper.find('.quest-item.is-editing').exists()).toBe(false)
      expect(wrapper.find('.save-btn').exists()).toBe(false)
      expect(wrapper.find('.btn-primary.btn-block').text()).toBe('Add Quest Challenge')
    })

    it('leaves edit mode when the edited quest is deleted', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
      const wrapper = await mountBuilder()
      await editButton(wrapper, 'Lock it up').trigger('click')
      const item = wrapper.findAll('.quest-item').find((li) => li.text().includes('Lock it up'))!
      await item.find('.delete-btn').trigger('click')
      await flushPromises()

      expect(api.deleteQuest).toHaveBeenCalledWith(11)
      expect(wrapper.find('.form-heading').text()).toBe('New quest')
      expect((wrapper.find('#questTitle').element as HTMLInputElement).value).toBe('')
      confirmSpy.mockRestore()
    })
  })
})
