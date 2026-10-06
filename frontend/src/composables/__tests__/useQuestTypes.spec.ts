import { describe, it, expect } from 'vitest'
import {
  QUEST_TYPES,
  CRITERIA_TYPES,
  questTypeFor,
  platformInfo,
  PLATFORMS,
  formatSessionLine,
  formatSessionTime,
  formatQuestWindow,
  TOOLS,
  questTypeTools,
  canDoQuest,
  toolsNeededText
} from '../useQuestTypes'

describe('QUEST_TYPES map', () => {
  it('covers all eleven criteria types with complete presentation data', () => {
    expect(CRITERIA_TYPES).toEqual([
      'osm_tags',
      'wikimedia_commons',
      'wikidata_entry',
      'wikidata_statement',
      'location_checkin',
      'osm_notes',
      'ohm_feature',
      'oss_contribution',
      'street_imagery',
      'mangrove_review',
      'maproulette_task'
    ])
    for (const type of CRITERIA_TYPES) {
      const info = QUEST_TYPES[type]
      expect(info.label, type).toBeTruthy()
      expect(info.shortLabel, type).toBeTruthy()
      expect(info.icon, type).toBeTruthy()
      expect(info.description, type).toBeTruthy()
      expect(info.helpApp, type).toBeTruthy()
      expect(info.colorToken, type).toMatch(/^--color-/)
      expect(info.color, type).toMatch(/^#[0-9a-f]{6}$/i)
    }
  })

  it('names the app participants should use', () => {
    expect(QUEST_TYPES.osm_tags.helpApp).toBe('StreetComplete / EveryDoor')
    expect(QUEST_TYPES.wikimedia_commons.helpApp).toBe('Commons app')
    expect(QUEST_TYPES.ohm_feature.helpApp).toBe('OHM iD editor')
    expect(QUEST_TYPES.oss_contribution.helpApp).toBe('GitHub')
  })

  it('flags only street_imagery as coming soon', () => {
    expect(CRITERIA_TYPES.filter((t) => QUEST_TYPES[t].comingSoon)).toEqual(['street_imagery'])
  })

  it('falls back gracefully for unknown types', () => {
    expect(questTypeFor('osm_tags')).toBe(QUEST_TYPES.osm_tags)
    const unknown = questTypeFor('teleportation')
    expect(unknown.label).toBe('teleportation')
    expect(unknown.icon).toBeTruthy()
    expect(questTypeFor(undefined).label).toBe('Quest')
  })
})

describe('platformInfo', () => {
  it('maps every submission platform onto a quest type icon', () => {
    for (const [platform, { type }] of Object.entries(PLATFORMS)) {
      expect(platformInfo(platform).icon).toBe(QUEST_TYPES[type].icon)
    }
    expect(platformInfo('github').label).toBe('GitHub')
  })

  it('prefers the server display name and survives unknown platforms', () => {
    expect(platformInfo('ohm', 'OpenHistoricalMap (OHM)').label).toBe('OpenHistoricalMap (OHM)')
    expect(platformInfo('mastodon').label).toBe('mastodon')
  })
})

describe('formatSessionTime', () => {
  it('uses the wall-clock time written in the ISO string, not the viewer time zone', () => {
    // 2026-11-04 is a Wednesday
    expect(formatSessionTime('2026-11-04T11:00:00-08:00')).toBe('Wed 11:00')
    expect(formatSessionTime('2026-11-03T16:10:00-08:00')).toBe('Tue 16:10')
  })

  it('returns an empty string for missing or malformed values', () => {
    expect(formatSessionTime(undefined)).toBe('')
    expect(formatSessionTime('Wednesday')).toBe('')
  })
})

describe('formatSessionLine', () => {
  it('formats title, speakers, time and room with the link', () => {
    const line = formatSessionLine({
      code: 'OHM01',
      title: 'OpenHistoricalMap: across the geoverse',
      speakers: ['Minh Nguyễn'],
      start: '2026-11-04T11:00:00-08:00',
      room: 'Beavis',
      track: 'Community of Practice',
      url: 'https://talks.osgeo.org/foss4g-na-2026/talk/OHM01/'
    })
    expect(line).toEqual({
      title: 'OpenHistoricalMap: across the geoverse',
      details: 'Minh Nguyễn · Wed 11:00 · Beavis',
      text: 'Inspired by: OpenHistoricalMap: across the geoverse — Minh Nguyễn · Wed 11:00 · Beavis',
      url: 'https://talks.osgeo.org/foss4g-na-2026/talk/OHM01/'
    })
  })

  it('joins several speakers and skips missing parts', () => {
    const line = formatSessionLine({ title: 'Open Transit Data', speakers: ['A. Siroky', 'B. Ritezel'] })
    expect(line?.text).toBe('Inspired by: Open Transit Data — A. Siroky, B. Ritezel')
    expect(line?.url).toBeNull()
  })

  it('handles hand-entered sessions with only a title or only a url', () => {
    expect(formatSessionLine({ title: 'Welcome Icebreaker BBQ' })?.text).toBe('Inspired by: Welcome Icebreaker BBQ')
    expect(formatSessionLine({ url: 'https://example.org/talk' })?.title).toBe('https://example.org/talk')
  })

  it('returns null for empty objects and null', () => {
    expect(formatSessionLine({})).toBeNull()
    expect(formatSessionLine(null)).toBeNull()
    expect(formatSessionLine(undefined)).toBeNull()
    expect(formatSessionLine({ title: '   ', speakers: [] })).toBeNull()
  })
})

describe('formatQuestWindow', () => {
  // Built from local-time Dates so the expectations hold in any test-runner time zone
  const local = (y: number, m: number, d: number, h: number, min = 0) => new Date(y, m - 1, d, h, min).toISOString()

  it('formats a same-day window as "Mon 18:00–20:00"', () => {
    // 2026-11-02 is a Monday
    expect(formatQuestWindow(local(2026, 11, 2, 18), local(2026, 11, 2, 20))).toBe('Mon 18:00–20:00')
  })

  it('shows both days when the window spans midnight', () => {
    expect(formatQuestWindow(local(2026, 11, 3, 18), local(2026, 11, 4, 2, 30))).toBe('Tue 18:00 – Wed 02:30')
  })

  it('handles open-ended and missing windows', () => {
    expect(formatQuestWindow(local(2026, 11, 4, 16), null)).toBe('From Wed 16:00')
    expect(formatQuestWindow(null, local(2026, 11, 4, 17))).toBe('Until Wed 17:00')
    expect(formatQuestWindow(null, null)).toBeNull()
    expect(formatQuestWindow('not a date', undefined)).toBeNull()
  })
})

describe('tools and canDoQuest', () => {
  it('maps every criteria type to the tools that make it doable', () => {
    for (const type of CRITERIA_TYPES) expect(questTypeTools[type], type).toBeDefined()
    const toolIds = TOOLS.map((tool) => tool.id)
    for (const tools of Object.values(questTypeTools)) {
      for (const tool of tools) expect(toolIds).toContain(tool)
    }
    // Every tool has a description and at least one https link
    for (const tool of TOOLS) {
      expect(tool.description, tool.id).toBeTruthy()
      expect(tool.links.length, tool.id).toBeGreaterThan(0)
      for (const link of tool.links) expect(link.url).toMatch(/^https:\/\//)
    }
  })

  it('needs any one of the listed tools', () => {
    expect(canDoQuest('osm_tags', ['everydoor'])).toBe(true)
    expect(canDoQuest('osm_tags', ['osm_web'])).toBe(true)
    expect(canDoQuest('osm_tags', ['commons', 'wikidata'])).toBe(false)
    expect(canDoQuest('osm_notes', ['streetcomplete'])).toBe(true)
    expect(canDoQuest('osm_notes', ['everydoor'])).toBe(false)
    expect(canDoQuest('ohm_feature', ['osm_web'])).toBe(false)
    expect(canDoQuest('ohm_feature', ['ohm_editor'])).toBe(true)
    expect(canDoQuest('wikimedia_commons', ['commons'])).toBe(true)
    expect(canDoQuest('wikidata_entry', ['wikidata'])).toBe(true)
    expect(canDoQuest('wikidata_statement', ['commons'])).toBe(false)
    expect(canDoQuest('oss_contribution', ['github'])).toBe(true)
    expect(canDoQuest('street_imagery', ['panoramax'])).toBe(true)
    expect(canDoQuest('street_imagery', [])).toBe(false)
    expect(canDoQuest('mangrove_review', ['mangrove'])).toBe(true)
    expect(canDoQuest('mangrove_review', ['osm_web'])).toBe(false)
    expect(canDoQuest('maproulette_task', ['maproulette'])).toBe(true)
    expect(canDoQuest('maproulette_task', ['streetcomplete'])).toBe(false)
    expect(toolsNeededText('maproulette_task')).toBe('MapRoulette (web, maproulette.org, OSM login)')
  })

  it('treats check-ins and unknown types as always doable', () => {
    expect(canDoQuest('location_checkin', [])).toBe(true)
    expect(canDoQuest('future_type', [])).toBe(true)
  })

  it('lists the needed tools as "A, B or C"', () => {
    expect(toolsNeededText('osm_tags')).toBe('StreetComplete, EveryDoor or OpenStreetMap web editor (iD)')
    expect(toolsNeededText('osm_notes')).toBe('OpenStreetMap web editor (iD) or StreetComplete')
    expect(toolsNeededText('wikidata_entry')).toBe('Wikidata')
    expect(toolsNeededText('location_checkin')).toBe('')
  })
})
