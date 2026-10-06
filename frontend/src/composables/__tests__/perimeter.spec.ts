import { describe, it, expect } from 'vitest'
import {
  bboxFromCorners,
  bboxToPolygon,
  polygonToBbox,
  bboxError,
  bboxToInputs,
  parseBboxInputs,
  formatCoord
} from '../perimeter'

const sacramento = { west: -121.509, south: 38.572, east: -121.481, north: 38.59 }

describe('bboxFromCorners', () => {
  it('normalises two opposite corners clicked in any order', () => {
    const ne = { lat: 38.59, lng: -121.481 }
    const sw = { lat: 38.572, lng: -121.509 }
    expect(bboxFromCorners(sw, ne)).toEqual(sacramento)
    expect(bboxFromCorners(ne, sw)).toEqual(sacramento)
    // North-west then south-east
    expect(bboxFromCorners({ lat: 38.59, lng: -121.509 }, { lat: 38.572, lng: -121.481 })).toEqual(sacramento)
  })
})

describe('bboxToPolygon', () => {
  it('builds a closed lon/lat ring', () => {
    const polygon = bboxToPolygon(sacramento)
    expect(polygon.type).toBe('Polygon')
    const ring = polygon.coordinates[0]
    expect(ring).toHaveLength(5)
    expect(ring[0]).toEqual([-121.509, 38.572])
    expect(ring[4]).toEqual(ring[0])
    // [lon, lat]: every first value is a longitude
    for (const [lon, lat] of ring) {
      expect([sacramento.west, sacramento.east]).toContain(lon)
      expect([sacramento.south, sacramento.north]).toContain(lat)
    }
  })

  it('round-trips through polygonToBbox', () => {
    expect(polygonToBbox(bboxToPolygon(sacramento))).toEqual(sacramento)
  })
})

describe('polygonToBbox', () => {
  it('reads the seeded FOSS4G NA perimeter (a rectangle)', () => {
    const seeded = {
      type: 'Polygon',
      coordinates: [[[-121.509, 38.572], [-121.481, 38.572], [-121.481, 38.59], [-121.509, 38.59], [-121.509, 38.572]]]
    }
    expect(polygonToBbox(seeded)).toEqual(sacramento)
  })

  it('accepts a clockwise or unclosed rectangle', () => {
    const clockwise = { type: 'Polygon', coordinates: [[[0, 0], [0, 1], [2, 1], [2, 0], [0, 0]]] }
    expect(polygonToBbox(clockwise)).toEqual({ west: 0, south: 0, east: 2, north: 1 })
    const unclosed = { type: 'Polygon', coordinates: [[[0, 0], [2, 0], [2, 1], [0, 1]]] }
    expect(polygonToBbox(unclosed)).toEqual({ west: 0, south: 0, east: 2, north: 1 })
  })

  it('returns null for anything that is not an axis-aligned rectangle', () => {
    const pentagon = { type: 'Polygon', coordinates: [[[0, 0], [2, 0], [3, 1], [1, 2], [-1, 1], [0, 0]]] }
    const rotated = { type: 'Polygon', coordinates: [[[0, 1], [1, 0], [2, 1], [1, 2], [0, 1]]] }
    const bowTie = { type: 'Polygon', coordinates: [[[0, 0], [2, 1], [2, 0], [0, 1], [0, 0]]] }
    const withHole = { type: 'Polygon', coordinates: [bboxToPolygon(sacramento).coordinates[0], [[0, 0], [1, 0], [1, 1], [0, 0]]] }
    expect(polygonToBbox(pentagon)).toBeNull()
    expect(polygonToBbox(rotated)).toBeNull()
    expect(polygonToBbox(bowTie)).toBeNull()
    expect(polygonToBbox(withHole)).toBeNull()
    expect(polygonToBbox({ type: 'MultiPolygon', coordinates: [] })).toBeNull()
    expect(polygonToBbox(null)).toBeNull()
  })
})

describe('bbox validation and inputs', () => {
  it('flags inverted, out-of-range and missing edges', () => {
    expect(bboxError(sacramento)).toBeNull()
    expect(bboxError({ ...sacramento, west: -121.4 })).toMatch(/West must be less than east/)
    expect(bboxError({ ...sacramento, south: 39 })).toMatch(/South must be less than north/)
    expect(bboxError({ ...sacramento, north: 91 })).toMatch(/between -90 and 90/)
    expect(bboxError({ ...sacramento, east: 181 })).toMatch(/between -180 and 180/)
    expect(bboxError({ ...sacramento, east: NaN })).toMatch(/all four/)
  })

  it('formats inputs to 6 decimals without trailing zeros', () => {
    expect(formatCoord(-121.50900000001)).toBe('-121.509')
    expect(formatCoord(38.1234567)).toBe('38.123457')
    expect(bboxToInputs(sacramento)).toEqual({ west: '-121.509', south: '38.572', east: '-121.481', north: '38.59' })
  })

  it('parses typed inputs: blank is "nothing yet", partial or invalid is an error', () => {
    expect(parseBboxInputs({ west: '', south: '', east: '', north: '' })).toEqual({ bbox: null, error: null })
    expect(parseBboxInputs(bboxToInputs(sacramento))).toEqual({ bbox: sacramento, error: null })
    expect(parseBboxInputs({ west: '-121.5', south: '', east: '', north: '' }).error).toMatch(/all four/)
    expect(parseBboxInputs({ west: '1', south: '1', east: '0', north: '2' }).error).toMatch(/West must be less/)
    // v-model on number inputs hands back numbers
    expect(parseBboxInputs({ west: 0, south: 0, east: 1, north: 1 } as any).bbox).toEqual({ west: 0, south: 0, east: 1, north: 1 })
  })
})
