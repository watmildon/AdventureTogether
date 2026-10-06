import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import EventTeamsView from '../views/backoffice/EventTeamsView.vue'

vi.mock('../api', async (importOriginal) => {
  const actual: any = await importOriginal()
  return {
    ...actual,
    api: {
      getTeams: vi.fn(),
      createTeam: vi.fn()
    }
  }
})

const member = (id: number, name: string, usernames: Record<string, string> = {}) => ({
  id, user_identifier: `u${id}`, display_name: name, joined_at: '',
  osm_username: '', wikimedia_username: '', github_username: '', ...usernames
})

const teams = [
  { id: 1, event: 2, name: 'Beta', join_code: 'BBB222', score: 10, member_count: 1, memberships: [member(1, 'Bo')], created_at: '' },
  {
    id: 2, event: 2, name: 'Alpha', join_code: 'AAA111', score: 40, member_count: 2,
    memberships: [member(2, 'Ana', { osm_username: 'ana_osm', github_username: 'ana-gh' }), member(3, 'Al')], created_at: ''
  }
]

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/backoffice/events/:id/teams', component: EventTeamsView }]
})

const mountTeams = async () => {
  router.push('/backoffice/events/2/teams')
  await router.isReady()
  const wrapper = mount(EventTeamsView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('EventTeamsView', () => {
  beforeEach(async () => {
    const { api } = await import('../api')
    vi.mocked(api.getTeams).mockReset().mockResolvedValue(teams as any)
    vi.mocked(api.createTeam).mockReset()
  })

  it('shows each team with join code, members, score and usernames, highest score first', async () => {
    const { api } = await import('../api')
    const wrapper = await mountTeams()
    expect(api.getTeams).toHaveBeenCalledWith('2')

    const rows = wrapper.findAll('tbody tr')
    expect(rows.map((r) => r.find('.team-name').text())).toEqual(['Alpha', 'Beta'])
    const alpha = rows[0]
    expect(alpha.find('.code').text()).toBe('AAA111')
    expect(alpha.text()).toContain('40')
    expect(alpha.text()).toContain('Ana')
    expect(alpha.text()).toContain('OSM: ana_osm · GitHub: ana-gh')
    expect(alpha.text()).toContain('no usernames given')
  })

  it('creates a team, shows its join code and reloads the list', async () => {
    const { api } = await import('../api')
    vi.mocked(api.createTeam).mockResolvedValue({ id: 3, event: 2, name: 'Gamma', join_code: 'GGG333', score: 0, member_count: 0, memberships: [], created_at: '' })
    const wrapper = await mountTeams()

    await wrapper.find('form.create-form').trigger('submit')
    expect(wrapper.text()).toContain('Give the team a name.')
    expect(api.createTeam).not.toHaveBeenCalled()

    await wrapper.find('#newTeamName').setValue('  Gamma ')
    await wrapper.find('form.create-form').trigger('submit')
    await flushPromises()

    expect(api.createTeam).toHaveBeenCalledWith('2', 'Gamma')
    expect(wrapper.find('.created-note').text()).toContain('GGG333')
    expect(api.getTeams).toHaveBeenCalledTimes(2)
    expect((wrapper.find('#newTeamName').element as HTMLInputElement).value).toBe('')
  })

  it('shows the API error when creating fails', async () => {
    const { api } = await import('../api')
    vi.mocked(api.createTeam).mockRejectedValue(new Error('The fields event, name must make a unique set.'))
    const wrapper = await mountTeams()
    await wrapper.find('#newTeamName').setValue('Alpha')
    await wrapper.find('form.create-form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('unique')
  })
})
