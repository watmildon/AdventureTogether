import { describe, it, expect, vi, afterEach } from 'vitest'
import { api } from '../api'

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
