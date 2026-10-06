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
      getLeaderboard: vi.fn(),
      getQuestStandings: vi.fn()
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

describe('QuestPanel value scoring', () => {
  const stamps = quest({
    id: 24,
    title: 'Stamped in Sacramento',
    criteria_type: 'wikimedia_commons',
    target_geometry: null,
    validation_rules: {
      target_count: 1,
      scoring: {
        value: { source: 'description', kind: 'year' },
        per_bucket: { size: 10, points: 5 },
        extreme_bonus: { direction: 'min', points: 25 }
      }
    }
  })
  const row = (overrides: Partial<QuestProgressData>): QuestProgressData => ({
    quest: 24, quest_title: 'Stamped in Sacramento', count: 2, target_count: 1, points_reward: 10,
    completed_at: '2026-11-03T20:00:00Z', points_awarded: true, ...overrides
  })
  const standings = (holders: number[], extreme: number) => ({
    quest: 24,
    extreme_value: extreme,
    extreme_holder_team_ids: holders,
    standings: [
      { team: 5, team_name: 'Rivals', awarded_points: 40, buckets: [1910], best_value: 1911, verified_count: 1 },
      { team: 4, team_name: 'Organisers', awarded_points: 45, buckets: [1920, 1950], best_value: 1923, verified_count: 2 }
    ]
  })

  it('loads standings for scoring quests through useQuestProgress and shows the bonus holder', async () => {
    const { api } = await import('../api')
    ;(api.getTeamProgress as any).mockResolvedValue([row({ awarded_points: 45, buckets: [1950, 1920], best_value: 1923 })])
    ;(api.getQuestStandings as any).mockResolvedValue(standings([4], 1923))

    const { progressByQuest, standingsByQuest, refresh } = useQuestProgress(2, ref(4), ref([24]))
    await refresh()
    expect(api.getQuestStandings).toHaveBeenCalledWith(24)

    const wrapper = mount(QuestPanel, {
      props: { quests: [stamps], progressByQuest: progressByQuest.value, standingsByQuest: standingsByQuest.value, hasTeam: true, teamId: 4 }
    })
    const card = wrapper.find('.quest-card')
    expect(card.find('.points').text()).toBe('10 pts, +5 per decade, +25 for the oldest')
    expect(card.find('.scoring-points').text()).toBe('45 pts held · Your oldest: 1923')
    expect(card.find('.scoring-buckets').text()).toBe('Decades found: 1920s, 1950s')
    expect(card.find('.scoring-bonus').text()).toBe('🏆 Your team holds the oldest (1923): +25')
    expect(card.find('.scoring-bonus').classes()).toContain('held')
  })

  it('names the team holding the bonus when it is not yours', () => {
    const wrapper = mount(QuestPanel, {
      props: {
        quests: [stamps],
        progressByQuest: new Map([[24, row({ awarded_points: 20, buckets: [1920, 1950], best_value: 1923 })]]),
        standingsByQuest: new Map([[24, standings([5], 1911)]]),
        hasTeam: true,
        teamId: 4
      }
    })
    expect(wrapper.find('.scoring-points').text()).toContain('20 pts held')
    expect(wrapper.find('.scoring-bonus').text()).toBe('Oldest so far: 1911, held by Rivals')
    expect(wrapper.find('.scoring-bonus').classes()).not.toContain('held')
  })

  it('shows only the standing without a team, and nothing extra on other quests', () => {
    const wrapper = mount(QuestPanel, {
      props: { quests: [stamps, quests[0]], standingsByQuest: new Map([[24, standings([5], 1911)]]) }
    })
    const cards = wrapper.findAll('.quest-card')
    expect(cards[0].find('.scoring-points').exists()).toBe(false)
    expect(cards[0].find('.scoring-bonus').text()).toBe('Oldest so far: 1911, held by Rivals')
    expect(cards[1].find('.scoring').exists()).toBe(false)
    expect(cards[1].find('.points').text()).toBe('40 pts')
  })

  it('does not fetch standings when no quest scores values', async () => {
    const { api } = await import('../api')
    ;(api.getQuestStandings as any).mockClear()
    const { refresh, standingsByQuest } = useQuestProgress(2, ref(4))
    await refresh()
    expect(api.getQuestStandings).not.toHaveBeenCalled()
    expect(standingsByQuest.value.size).toBe(0)
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
