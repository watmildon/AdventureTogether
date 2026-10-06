import { describe, it, expect } from 'vitest'
import { useDeepLinks } from '../useDeepLinks'

describe('useDeepLinks Composable', () => {
  const { getDeepLinks } = useDeepLinks()

  it('generates valid URI schemes for StreetComplete and EveryDoor', () => {
    const lat = 37.774929
    const lng = -122.419416

    const links = getDeepLinks(lat, lng, 18)

    // StreetComplete deep link
    expect(links.streetCompleteUrl).toBe('streetcomplete://#map=18/37.774929/-122.419416')

    // EveryDoor deep link
    expect(links.everyDoorUrl).toBe('everydoor://?lat=37.774929&lon=-122.419416&zoom=18')

    // Web Fallback links
    expect(links.osmWebEditorUrl).toBe('https://www.openstreetmap.org/edit#map=18/37.774929/-122.419416')
    expect(links.osmWebViewUrl).toBe('https://www.openstreetmap.org/#map=18/37.774929/-122.419416')
  })

  it('links to WikiShootMe at zoom 17 whatever the map zoom', () => {
    const links = getDeepLinks(38.579, -121.4899, 18)
    expect(links.wikiShootMeUrl).toBe('https://wikishootme.toolforge.org/#lat=38.579000&lng=-121.489900&zoom=17')
    expect(getDeepLinks(38.579, -121.4899).wikiShootMeUrl).toContain('&zoom=17')
  })
})
