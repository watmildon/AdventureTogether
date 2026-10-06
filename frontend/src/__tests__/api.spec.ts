import { describe, it, expect, vi, afterEach } from 'vitest'
import { api, ApiError } from '../api'

describe('api.joinTeam', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const lastBody = (fetchMock: ReturnType<typeof vi.fn>) => JSON.parse(fetchMock.mock.calls[0][1].body)

  it("always sends the three username fields, trimmed, with '' for blank so the API can clear them", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ message: 'Joined', team: {}, membership: {} }) })
    vi.stubGlobal('fetch', fetchMock)

    await api.joinTeam('ORG123', 'device-1', 'Alice', { osm_username: ' alice_osm ', wikimedia_username: '  ' })

    expect(lastBody(fetchMock)).toEqual({
      join_code: 'ORG123',
      user_identifier: 'device-1',
      display_name: 'Alice',
      osm_username: 'alice_osm',
      wikimedia_username: '',
      github_username: ''
    })
  })

  it('sends empty usernames when none are given', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)

    await api.joinTeam('ORG123', 'device-1', 'Alice')

    expect(lastBody(fetchMock)).toMatchObject({ osm_username: '', wikimedia_username: '', github_username: '' })
  })
})

describe('back-office api helpers', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('createEvent surfaces DRF field errors on ApiError.fields', async () => {
    const body = { schedule_url: ['Schedule URL host "example.com" is not allowed.'], hashtag: 'This field may not be blank.' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 400, json: async () => body }))

    const error: any = await api.createEvent({ title: 'x' }).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(400)
    expect(error.fields).toEqual({
      schedule_url: ['Schedule URL host "example.com" is not allowed.'],
      hashtag: ['This field may not be blank.']
    })
    expect(error.message).toBe('schedule_url: Schedule URL host "example.com" is not allowed.')
  })

  it('updateEvent PATCHes only the given fields', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 2, is_active: false }) })
    vi.stubGlobal('fetch', fetchMock)
    await api.updateEvent(2, { is_active: false })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/events/2/')
    expect(fetchMock.mock.calls[0][1].method).toBe('PATCH')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ is_active: false })
  })

  it('countSubmissions reads the paginated count with the is_verified filter', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ count: 7, results: [] }) })
    vi.stubGlobal('fetch', fetchMock)
    expect(await api.countSubmissions(2, false)).toBe(7)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/submissions/?event=2&is_verified=false')
  })

  it('triggerHarvest throws the server message on 404', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({ error: 'Event 9 not found or inactive.', stats: {} }) }))
    const error: any = await api.triggerHarvest(9).catch((e) => e)
    expect(error.status).toBe(404)
    expect(error.message).toBe('Event 9 not found or inactive.')
  })
})
