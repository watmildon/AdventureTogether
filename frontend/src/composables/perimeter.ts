/**
 * Event perimeter helpers for the back-office event form: an axis-aligned bounding box
 * (west/south/east/north, degrees) <-> a closed GeoJSON Polygon ring in [lon, lat] order.
 *
 * Kept free of Vue and Leaflet so they can be unit-tested directly.
 */

export interface Bbox {
  west: number
  south: number
  east: number
  north: number
}

/** The four bbox inputs as typed by the host (strings, possibly blank). */
export type BboxInputs = Record<keyof Bbox, string>

export interface LatLngLike {
  lat: number
  lng: number
}

export interface GeoJsonPolygon {
  type: 'Polygon'
  coordinates: number[][][]
}

/** A bbox from two opposite corners clicked in any order. */
export function bboxFromCorners(a: LatLngLike, b: LatLngLike): Bbox {
  return {
    west: Math.min(a.lng, b.lng),
    south: Math.min(a.lat, b.lat),
    east: Math.max(a.lng, b.lng),
    north: Math.max(a.lat, b.lat)
  }
}

/** Why a bbox cannot be used, or null when it is fine. */
export function bboxError(bbox: Bbox): string | null {
  const values = [bbox.west, bbox.south, bbox.east, bbox.north]
  if (!values.every(Number.isFinite)) return 'Enter all four edges as numbers.'
  if ([bbox.west, bbox.east].some((lon) => lon < -180 || lon > 180)) return 'West and east must be between -180 and 180.'
  if ([bbox.south, bbox.north].some((lat) => lat < -90 || lat > 90)) return 'South and north must be between -90 and 90.'
  if (bbox.west >= bbox.east) return 'West must be less than east.'
  if (bbox.south >= bbox.north) return 'South must be less than north.'
  return null
}

/** Closed ring, counter-clockwise from the south-west corner, as RFC 7946 recommends for exteriors. */
export function bboxToPolygon(bbox: Bbox): GeoJsonPolygon {
  const { west, south, east, north } = bbox
  return {
    type: 'Polygon',
    coordinates: [[
      [west, south],
      [east, south],
      [east, north],
      [west, north],
      [west, south]
    ]]
  }
}

/**
 * The bbox of a polygon that is an axis-aligned rectangle (one ring, four corners, edges
 * parallel to the axes, closed or not), or null for anything else, e.g. a hand-drawn
 * perimeter, which the form then shows as-is instead of filling the inputs.
 */
export function polygonToBbox(geometry: any): Bbox | null {
  if (!geometry || geometry.type !== 'Polygon' || !Array.isArray(geometry.coordinates)) return null
  if (geometry.coordinates.length !== 1) return null
  let ring: number[][] = geometry.coordinates[0]
  if (!Array.isArray(ring)) return null
  if (!ring.every((p) => Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]))) return null

  const first = ring[0]
  const last = ring[ring.length - 1]
  if (ring.length === 5 && first[0] === last[0] && first[1] === last[1]) ring = ring.slice(0, 4)
  if (ring.length !== 4) return null

  const lons = [...new Set(ring.map((p) => p[0]))]
  const lats = [...new Set(ring.map((p) => p[1]))]
  if (lons.length !== 2 || lats.length !== 2) return null

  // Each edge must be horizontal or vertical: rules out a "bow tie" ordering of the corners
  for (let i = 0; i < 4; i++) {
    const [x1, y1] = ring[i]
    const [x2, y2] = ring[(i + 1) % 4]
    if (x1 !== x2 && y1 !== y2) return null
  }
  // ...and all four corners distinct
  if (new Set(ring.map((p) => `${p[0]},${p[1]}`)).size !== 4) return null

  return { west: Math.min(...lons), south: Math.min(...lats), east: Math.max(...lons), north: Math.max(...lats) }
}

/** Degrees rounded to 6 decimals (about 10 cm), without trailing zeros, for the inputs. */
export function formatCoord(value: number): string {
  return String(Number(value.toFixed(6)))
}

export function bboxToInputs(bbox: Bbox): BboxInputs {
  return {
    west: formatCoord(bbox.west),
    south: formatCoord(bbox.south),
    east: formatCoord(bbox.east),
    north: formatCoord(bbox.north)
  }
}

/**
 * Parses the four inputs. Returns {bbox: null, error: null} while all are blank (nothing
 * entered yet), and an error message when they are partly filled or invalid.
 */
export function parseBboxInputs(inputs: BboxInputs): { bbox: Bbox | null; error: string | null } {
  const raw = [inputs.west, inputs.south, inputs.east, inputs.north].map((v) => String(v ?? '').trim())
  if (raw.every((v) => v === '')) return { bbox: null, error: null }
  const [west, south, east, north] = raw.map((v) => (v === '' ? NaN : Number(v)))
  const bbox = { west, south, east, north }
  const error = bboxError(bbox)
  return error ? { bbox: null, error } : { bbox, error: null }
}
