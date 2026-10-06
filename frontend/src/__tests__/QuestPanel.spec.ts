import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import QuestPanel from '../components/QuestPanel.vue'
import { useQuestProgress, readStoredTeamId, readStoredTeam } from '../composables/useQuestProgress'
import type { QuestData, QuestProgressData } from '../api'

// Progress and leaderboard come from the API; stub the client so the panel is fed by the real composable
vi.mock('../api', async (importOriginal) => {
  const actual: any = await importOriginal()
  return {
    ...actual,
    api: {
      getTeamProgress: vi.fn(),
      getLeaderboard: vi.fn()
    }
  }
})

const quest = (overrides: Partial<QuestData>): QuestData => ({
  id: 1,
  event: 2,
  title: 'Quest',
  description: '',
  target_geometry: { type: 'Point', coordinates: [-121.49, 38.579] },
  criteria_type: 'osm_tags',
  validation_rules: {},
  points_reward: 10,
  is_active: true,
  inspired_by: {},
  window_start: null,
  window_end: null,
  target_count: 1,
  created_at: '2026-10-01T00:00:00Z',
  ...overrides
})

const quests: QuestData[] = [
  quest({
    id: 7,
    title: 'Farm-to-fork hours',
    points_reward: 40,
    target_count: 5,
    inspired_by: {
      title: 'Farm-to-fork data',
      speakers: ['Jane Mapper'],
      start: '2026-11-03T16:00:00-08:00',
      room: 'Beavis',
      url: 'https://talks.osgeo.org/foss4g-na-2026/talk/ABC123/'
    }
  }),
  quest({ id: 8, title: 'Icebreaker check-in', criteria_type: 'location_checkin', points_reward: 10 }),
  quest({ id: 13, title: 'Close a Note', criteria_type: 'osm_notes', target_geometry: null })
]

const progressRows: QuestProgressData[] = [
  { quest: 7, quest_title: 'Farm-to-fork hours', count: 3, target_count: 5, points_reward: 40, completed_at: null, points_awarded: false },
  { quest: 8, quest_title: 'Icebreaker check-in', count: 1, target_count: 1, points_reward: 10, completed_at: '2026-11-03T02:14:09Z', points_awarded: true },
  { quest: 13, quest_title: 'Close a Note', count: 0, target_count: 1, points_reward: 20, completed_at: null, points_awarded: false }
]

describe('QuestPanel with team progress', () => {
  beforeEach(async () => {
    localStorage.clear()
    const { api } = await import('../api')
    ;(api.getTeamProgress as any).mockResolvedValue(progressRows)
    ;(api.getLeaderboard as any).mockResolvedValue([])
  })

  it('renders type, points, progress, completion and the inspired-by link', async () => {
    const { api } = await import('../api')
    const { progressByQuest, refresh } = useQuestProgress(2, ref(4))
    await refresh()
    expect(api.getTeamProgress).toHaveBeenCalledWith(4)

    const wrapper = mount(QuestPanel, { props: { quests, progressByQuest: progressByQuest.value, hasTeam: true } })
    const cards = wrapper.findAll('.quest-card')
    expect(cards).toHaveLength(3)

    // Counted quest: type, points, 3/5 and the session line with its link
    expect(cards[0].text()).toContain('OSM')
    expect(cards[0].text()).toContain('40 pts')
    expect(cards[0].text()).toContain('3/5')
    expect(cards[0].find('.bar-fill').attributes('style')).toContain('width: 60%')
    expect(cards[0].text()).toContain('Inspired by:')
    expect(cards[0].text()).toContain('Jane Mapper · Tue 16:00 · Beavis')
    const link = cards[0].find('.inspired a')
    expect(link.text()).toBe('Farm-to-fork data')
    expect(link.attributes('href')).toBe('https://talks.osgeo.org/foss4g-na-2026/talk/ABC123/')
    expect(cards[0].classes()).not.toContain('complete')

    // Completed check-in
    expect(cards[1].text()).toContain('Check-in')
    expect(cards[1].text()).toContain('1/1')
    expect(cards[1].text()).toContain('✓ Done')
    expect(cards[1].classes()).toContain('complete')

    // No session and no target geometry: no inspired line, no map button
    expect(cards[2].find('.inspired').exists()).toBe(false)
    expect(cards[2].find('.show-btn').exists()).toBe(false)
    expect(cards[2].text()).toContain('Anywhere in the event area')
  })

  it('shows only the target without a team, plus check-in state', () => {
    const wrapper = mount(QuestPanel, { props: { quests, checkins: { 8: 'in_range' } } })
    const cards = wrapper.findAll('.quest-card')
    expect(cards[0].text()).toContain('Target: 5')
    expect(cards[0].find('.bar').exists()).toBe(false)
    expect(cards[1].text()).toContain("You're here")
  })

  it('distinguishes dwelling from checked in', () => {
    const dwelling = mount(QuestPanel, { props: { quests, checkins: { 8: 'dwelling' } } })
    expect(dwelling.findAll('.quest-card')[1].text()).toContain("You're here, stay a few minutes")
    expect(dwelling.findAll('.quest-card')[1].text()).not.toContain('Checked in')

    const verified = mount(QuestPanel, { props: { quests, checkins: { 8: 'verified' } } })
    expect(verified.findAll('.quest-card')[1].text()).toContain('✓ Checked in')
  })

  it('notes "new elements only" on osm_tags quests that count created elements', () => {
    const created = quest({ id: 21, title: 'Emergency ready', validation_rules: { action: 'create' } })
    const wrapper = mount(QuestPanel, { props: { quests: [created, quests[0]] } })
    const cards = wrapper.findAll('.quest-card')
    expect(cards[0].find('.help-app').text()).toBe('Use: StreetComplete / EveryDoor · new elements only')
    expect(cards[1].find('.help-app').text()).not.toContain('new elements only')
  })

  it('emits show-on-map with the quest', async () => {
    const wrapper = mount(QuestPanel, { props: { quests } })
    await wrapper.findAll('.show-btn')[0].trigger('click')
    expect(wrapper.emitted('show-on-map')?.[0]).toEqual([quests[0]])
  })
})

describe('useQuestProgress', () => {
  it('skips the progress call without a team but still loads the leaderboard', async () => {
    const { api } = await import('../api')
    ;(api.getTeamProgress as any).mockClear()
    ;(api.getLeaderboard as any).mockResolvedValue([{ id: 1, name: 'Team Compass', score: 15, member_count: 2, completed_quests: 1 }])

    const { progress, leaderboard, refresh } = useQuestProgress(1, ref(null))
    await refresh()
    await flushPromises()
    expect(api.getTeamProgress).not.toHaveBeenCalled()
    expect(progress.value).toEqual([])
    expect(leaderboard.value[0].name).toBe('Team Compass')
  })

  it('reads the team id only from the event-scoped record, never the global key', () => {
    localStorage.clear()
    expect(readStoredTeamId(2)).toBeNull()
    // The global key holds whichever team was joined last, possibly for another event
    localStorage.setItem('team_id', '9')
    expect(readStoredTeamId(2)).toBeNull()
    localStorage.setItem('team_for_event_2', JSON.stringify({ id: 4, name: 'Organisers' }))
    expect(readStoredTeamId(2)).toBe(4)
    expect(readStoredTeam(2)).toEqual({ id: 4, name: 'Organisers' })
  })

  it('does not carry a team joined for event 1 over to event 2', () => {
    localStorage.clear()
    localStorage.setItem('team_for_event_1', JSON.stringify({ id: 4, name: 'Organisers' }))
    localStorage.setItem('team_id', '4')
    localStorage.setItem('team_name', 'Organisers')
    expect(readStoredTeamId(1)).toBe(4)
    expect(readStoredTeamId(2)).toBeNull()
    expect(readStoredTeam(2)).toBeNull()
  })

  it('treats a corrupt event-scoped record as no team', () => {
    localStorage.clear()
    localStorage.setItem('team_for_event_2', '{not json')
    expect(readStoredTeamId(2)).toBeNull()
  })
})
