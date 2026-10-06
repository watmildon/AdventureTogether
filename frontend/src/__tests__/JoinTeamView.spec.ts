import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import JoinTeamView from '../views/JoinTeamView.vue'
import { createRouter, createMemoryHistory } from 'vue-router'

vi.mock('../api', async (importOriginal) => {
  const actual: any = await importOriginal()
  return {
    ...actual,
    api: {
      getTeams: vi.fn().mockResolvedValue([]),
      createTeam: vi.fn(),
      joinTeam: vi.fn()
    }
  }
})

const team = { id: 4, event: 1, name: 'Organisers', join_code: 'ORG123', score: 0, member_count: 1, memberships: [], created_at: '' }

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    {
      path: '/events/:id/join',
      name: 'join-team',
      component: JoinTeamView
    },
    {
      path: '/events/:id/map',
      name: 'event-map',
      component: { template: '<div>Event Map</div>' }
    }
  ]
})

describe('JoinTeamView Component', () => {
  beforeEach(async () => {
    vi.restoreAllMocks()
    localStorage.clear()
    // restoreAllMocks clears mock implementations, so re-apply the team list default
    const { api } = await import('../api')
    ;(api.getTeams as any).mockResolvedValue([])
  })

  it('renders tab controls for joining and creating teams', async () => {
    router.push('/events/1/join')
    await router.isReady()

    const wrapper = mount(JoinTeamView, {
      global: {
        plugins: [router]
      }
    })

    expect(wrapper.text()).toContain('Team Management')
    expect(wrapper.text()).toContain('Join Existing Team')
    expect(wrapper.text()).toContain('Create New Team')
  })

  it('switches between join code tab and create team tab', async () => {
    router.push('/events/1/join')
    await router.isReady()

    const wrapper = mount(JoinTeamView, {
      global: {
        plugins: [router]
      }
    })

    // Initially in join tab
    expect(wrapper.find('#joinCode').exists()).toBe(true)
    expect(wrapper.find('#teamName').exists()).toBe(false)

    // Switch to create tab
    const buttons = wrapper.findAll('.tab-controls button')
    await buttons[1].trigger('click')

    expect(wrapper.find('#teamName').exists()).toBe(true)
    expect(wrapper.find('#joinCode').exists()).toBe(false)
  })

  it('sends and remembers platform usernames when joining an existing team', async () => {
    const { api } = await import('../api')
    ;(api.joinTeam as any).mockResolvedValue({ message: 'Joined', team, membership: {} })
    localStorage.setItem('participant_id', 'device-1')

    router.push('/events/1/join')
    await router.isReady()
    const wrapper = mount(JoinTeamView, { global: { plugins: [router] } })

    expect(wrapper.text()).toContain('So your edits are credited to your team.')
    await wrapper.find('#displayName').setValue('Alice')
    await wrapper.find('#osmUsername').setValue(' alice_osm ')
    await wrapper.find('#githubUsername').setValue('alice-gh')
    await wrapper.find('#joinCode').setValue('ORG123')
    await wrapper.find('.tab-content .btn').trigger('click')
    await flushPromises()

    expect(api.joinTeam).toHaveBeenCalledWith('ORG123', 'device-1', 'Alice', {
      osm_username: 'alice_osm',
      wikimedia_username: '',
      github_username: 'alice-gh'
    })
    expect(localStorage.getItem('participant_osm_username')).toBe('alice_osm')
    expect(localStorage.getItem('participant_wikimedia_username')).toBeNull()
    expect(localStorage.getItem('participant_github_username')).toBe('alice-gh')
    expect(localStorage.getItem('team_id')).toBe('4')
    expect(localStorage.getItem('team_name')).toBe('Organisers')
    expect(JSON.parse(localStorage.getItem('team_for_event_1')!).id).toBe(4)
  })

  it('prefills stored usernames and sends them on the create-then-join path', async () => {
    const { api } = await import('../api')
    ;(api.createTeam as any).mockResolvedValue(team)
    ;(api.joinTeam as any).mockResolvedValue({ message: 'Joined', team, membership: {} })
    localStorage.setItem('participant_id', 'device-2')
    localStorage.setItem('participant_wikimedia_username', 'Alice (WMF)')

    router.push('/events/1/join')
    await router.isReady()
    const wrapper = mount(JoinTeamView, { global: { plugins: [router] } })

    expect((wrapper.find('#wikimediaUsername').element as HTMLInputElement).value).toBe('Alice (WMF)')
    await wrapper.find('#displayName').setValue('Alice')
    await wrapper.findAll('.tab-controls button')[1].trigger('click')
    await wrapper.find('#teamName').setValue('Organisers')
    await wrapper.find('.tab-content .btn').trigger('click')
    await flushPromises()

    expect(api.createTeam).toHaveBeenCalledWith('1', 'Organisers')
    // All three fields are sent; blanks as '' (the API clears on '' and keeps on omission)
    expect(api.joinTeam).toHaveBeenCalledWith('ORG123', 'device-2', 'Alice', {
      osm_username: '',
      wikimedia_username: 'Alice (WMF)',
      github_username: ''
    })
    expect(localStorage.getItem('team_id')).toBe('4')
  })

  it('sends an empty string for a username the participant cleared', async () => {
    const { api } = await import('../api')
    ;(api.joinTeam as any).mockResolvedValue({ message: 'Joined', team, membership: {} })
    localStorage.setItem('participant_id', 'device-3')
    localStorage.setItem('participant_osm_username', 'old_osm')
    localStorage.setItem('participant_github_username', 'old-gh')

    router.push('/events/1/join')
    await router.isReady()
    const wrapper = mount(JoinTeamView, { global: { plugins: [router] } })

    expect((wrapper.find('#osmUsername').element as HTMLInputElement).value).toBe('old_osm')
    await wrapper.find('#displayName').setValue('Alice')
    await wrapper.find('#osmUsername').setValue('   ')
    await wrapper.find('#joinCode').setValue('ORG123')
    await wrapper.find('.tab-content .btn').trigger('click')
    await flushPromises()

    expect(api.joinTeam).toHaveBeenCalledWith('ORG123', 'device-3', 'Alice', {
      osm_username: '',
      wikimedia_username: '',
      github_username: 'old-gh'
    })
    expect(localStorage.getItem('participant_osm_username')).toBeNull()
    expect(localStorage.getItem('participant_github_username')).toBe('old-gh')
  })
})
