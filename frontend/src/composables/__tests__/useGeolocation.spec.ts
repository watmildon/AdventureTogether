import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  useGeolocation,
  readSimulatedPosition,
  clearSimulatedPosition,
  SIMULATED_GPS_KEY
} from '../useGeolocation'

// The composable pings the backend as soon as it has coordinates; stub the API client.
vi.mock('../../api', () => ({
  api: { pingLocation: vi.fn().mockResolvedValue({}) }
}))

describe('useGeolocation Composable', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('initializes with default privacy visibility and foreground state', () => {
    const { visibility, isForeground, setVisibility } = useGeolocation(1)

    expect(visibility.value).toBe('team')
    expect(isForeground.value).toBe(true)

    // Update visibility to whole quest
    setVisibility('quest')
    expect(visibility.value).toBe('quest')
    expect(localStorage.getItem('privacy_visibility')).toBe('quest')
  })
})

describe('Simulated GPS position (testing aid)', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('reads ?lat and ?lng from a query string and persists them', () => {
    const position = readSimulatedPosition('?lat=37.781&lng=-122.412')

    expect(position).toEqual({ lat: 37.781, lng: -122.412 })
    expect(JSON.parse(localStorage.getItem(SIMULATED_GPS_KEY)!)).toEqual({ lat: 37.781, lng: -122.412 })
  })

  it('falls back to the persisted position when the query string has none', () => {
    localStorage.setItem(SIMULATED_GPS_KEY, JSON.stringify({ lat: 51.5, lng: -0.12 }))

    expect(readSimulatedPosition('')).toEqual({ lat: 51.5, lng: -0.12 })
  })

  it('ignores malformed query values and corrupt stored values', () => {
    expect(readSimulatedPosition('?lat=abc&lng=1')).toBeNull()

    localStorage.setItem(SIMULATED_GPS_KEY, 'not json')
    expect(readSimulatedPosition('')).toBeNull()
  })

  it('clearSimulatedPosition removes the persisted value', () => {
    localStorage.setItem(SIMULATED_GPS_KEY, JSON.stringify({ lat: 1, lng: 2 }))
    clearSimulatedPosition()

    expect(localStorage.getItem(SIMULATED_GPS_KEY)).toBeNull()
  })

  it('startTracking uses the simulated position instead of the Geolocation API', async () => {
    localStorage.setItem(SIMULATED_GPS_KEY, JSON.stringify({ lat: 37.781, lng: -122.412 }))
    const { api } = await import('../../api')

    const { coords, isSimulated, isTracking, error, startTracking, stopTracking } = useGeolocation(1)
    startTracking()

    expect(isSimulated.value).toBe(true)
    expect(isTracking.value).toBe(true)
    expect(error.value).toBeNull()
    expect(coords.value).toEqual({ lat: 37.781, lng: -122.412 })

    // A ping is sent immediately with the simulated coordinates
    expect(api.pingLocation).toHaveBeenCalledWith(
      expect.objectContaining({ event: 1, latitude: 37.781, longitude: -122.412 })
    )

    // ...and again on the 10 second heartbeat
    const callsBefore = (api.pingLocation as any).mock.calls.length
    vi.advanceTimersByTime(10000)
    expect((api.pingLocation as any).mock.calls.length).toBe(callsBefore + 1)

    stopTracking()
    expect(isTracking.value).toBe(false)
  })

  it('startTracking reports an error when no simulation is set and the browser lacks geolocation', () => {
    // jsdom does not implement navigator.geolocation
    const { isSimulated, isTracking, error, startTracking } = useGeolocation(1)
    startTracking()

    expect(isSimulated.value).toBe(false)
    expect(isTracking.value).toBe(false)
    expect(error.value).toMatch(/not supported/i)
  })

  it('persists a generated participant id and exposes the latest ping response', async () => {
    localStorage.setItem(SIMULATED_GPS_KEY, JSON.stringify({ lat: 38.579, lng: -121.49 }))
    const { api } = await import('../../api')
    const response = { id: 1, checkins: [{ quest: 8, quest_title: 'Icebreaker check-in', status: 'in_range', distance_m: 12 }] }
    ;(api.pingLocation as any).mockResolvedValueOnce(response)

    const { userIdentifier, lastPing, startTracking, stopTracking } = useGeolocation(2)
    expect(userIdentifier).toMatch(/^user-/)
    expect(localStorage.getItem('participant_id')).toBe(userIdentifier)
    // A second instance (e.g. after a reload) reuses the same id
    expect(useGeolocation(2).userIdentifier).toBe(userIdentifier)

    startTracking()
    await vi.waitFor(() => expect(lastPing.value).toEqual(response))
    stopTracking()
  })
})
