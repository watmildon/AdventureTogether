import { describe, it, expect } from 'vitest'
import { areaProperties, targetsSummary, targetsCardLine } from '../questTargets'
import { targetPopupHtml } from '../questLayers'

describe('questTargets', () => {
  it('reads the quest properties like the backend (P18 by default, invalid ids dropped)', () => {
    expect(areaProperties({ validation_rules: {} })).toEqual(['P18'])
    expect(areaProperties({ validation_rules: { properties: ['p18', 'P373', 'nope'] } })).toEqual(['P18', 'P373'])
    expect(areaProperties({ validation_rules: { properties: 'P373, P18' } })).toEqual(['P373', 'P18'])
    expect(areaProperties({ validation_rules: { properties: [] } })).toEqual(['P18'])
  })

  it('words the count for photos and for other properties', () => {
    expect(targetsSummary(113, ['P18'])).toBe('113 nearby items need a photo')
    expect(targetsSummary(1, ['P18'])).toBe('1 nearby item needs a photo')
    expect(targetsSummary(4, ['P18', 'P373'])).toBe('4 nearby items still lack P18 / P373')
  })

  it('walks the card line through not loaded, loading, loaded and error', () => {
    expect(targetsCardLine(undefined, ['P18'])).toEqual({ text: 'Nearby items that need a photo', button: 'Show on map', busy: false })
    expect(targetsCardLine({ status: 'loading', count: 0, shown: false }, ['P18']).busy).toBe(true)
    expect(targetsCardLine({ status: 'loaded', count: 113, shown: true }, ['P18'])).toEqual({
      text: '113 nearby items need a photo',
      button: 'Hide from map',
      busy: false
    })
    expect(targetsCardLine({ status: 'loaded', count: 113, shown: false }, ['P18']).button).toBe('Show on map')
    expect(targetsCardLine({ status: 'error', count: 0, shown: false }, ['P18']).button).toBe('Retry')
  })

  it('builds an escaped popup with the WikiShootMe and Wikidata links', () => {
    const html = targetPopupHtml({
      qid: 'Q100',
      label: 'Tower <Theatre>',
      lat: 38.5799,
      lon: -121.494,
      wikidata_url: 'https://www.wikidata.org/wiki/Q100',
      wikishootme_url: 'https://wikishootme.toolforge.org/#lat=38.5799&lng=-121.494&zoom=18'
    })
    expect(html).toContain('<strong>Tower &lt;Theatre&gt;</strong>')
    expect(html).toContain('href="https://wikishootme.toolforge.org/#lat=38.5799&amp;lng=-121.494&amp;zoom=18" target="_blank" rel="noopener">Open in WikiShootMe</a>')
    expect(html).toContain('href="https://www.wikidata.org/wiki/Q100" target="_blank" rel="noopener">Wikidata (Q100)</a>')
  })
})
