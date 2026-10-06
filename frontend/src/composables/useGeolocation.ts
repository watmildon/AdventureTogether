/**
 * Composable for Privacy-Preserving Foreground Geolocation Sharing.
 * Strictly transmits coordinates while the application is active in the foreground.
 */

import { ref, onMounted, onUnmounted, getCurrentInstance } from 'vue'
import { api, type LocationPingData } from '../api'
import { ensureParticipantId } from './participantProfile'

export type VisibilityTier = 'nobody' | 'team' | 'quest'

export interface SimulatedPosition {
  lat: number
  lng: number
}

/** localStorage key under which a simulated GPS position is persisted. */
export const SIMULATED_GPS_KEY = 'simulated_gps'

/**
 * Simulated positions are only honoured in dev builds, or when a production
 * build is explicitly started with VITE_ALLOW_SIMULATED_GPS=true (e.g. staging).
 */
const simulationAllowed = (): boolean =>
  Boolean(import.meta.env.DEV) || import.meta.env.VITE_ALLOW_SIMULATED_GPS === 'true'

/**
 * Returns a simulated GPS position for testing, or null when none is configured.
 *
 * Sources, in priority order:
 *   1. `?lat=<lat>&lng=<lng>` on the current URL. When present it is also
 *      persisted to localStorage so navigation keeps using it.
 *   2. A previously persisted position in localStorage.
 *
 * Open the map as e.g. `/events/1/map?lat=37.781&lng=-122.412` to activate it.
 */
export function readSimulatedPosition(search: string = window.location.search): SimulatedPosition | null {
  if (!simulationAllowed()) return null

  const params = new URLSearchParams(search)
  const lat = parseFloat(params.get('lat') ?? '')
  const lng = parseFloat(params.get('lng') ?? '')
  if (Number.isFinite(lat) && Number.isFinite(lng)) {
    const position = { lat, lng }
    localStorage.setItem(SIMULATED_GPS_KEY, JSON.stringify(position))
    return position
  }

  try {
    const stored = localStorage.getItem(SIMULATED_GPS_KEY)
    if (!stored) return null
    const parsed = JSON.parse(stored)
    if (Number.isFinite(parsed?.lat) && Number.isFinite(parsed?.lng)) {
      return { lat: parsed.lat, lng: parsed.lng }
    }
  } catch {
    // Corrupt value: ignore and fall through to real GPS
  }
  return null
}

/** Removes any persisted simulated position so real GPS is used again. */
export function clearSimulatedPosition(): void {
  localStorage.removeItem(SIMULATED_GPS_KEY)
}

export function useGeolocation(eventId: number | string) {
  const coords = ref<{ lat: number; lng: number } | null>(null)
  const accuracy = ref<number | null>(null)
  const isForeground = ref<boolean>(document.visibilityState === 'visible')
  const visibility = ref<VisibilityTier>(
    (localStorage.getItem('privacy_visibility') as VisibilityTier) || 'team'
  )
  const isTracking = ref<boolean>(false)
  const isSimulated = ref<boolean>(false)
  const error = ref<string | null>(null)
  const lastPingTime = ref<Date | null>(null)
  /** Latest ping response; carries `checkins` once the server's check-in matcher runs. */
  const lastPing = ref<LocationPingData | null>(null)

  let watchId: number | null = null
  let heartbeatTimer: any = null

  // Persist a generated id so pings, the "Active Teammates" filter and check-ins all
  // refer to the same participant across reloads (JoinTeamView uses the same key).
  const userIdentifier: string = ensureParticipantId()
  const displayName = localStorage.getItem('participant_name') || 'Anonymous Mapper'

  /**
   * Transmits a location ping to the backend API if foregrounded.
   */
  const sendPing = async () => {
    if (!coords.value || !isForeground.value || !isTracking.value) return

    try {
      lastPing.value = await api.pingLocation({
        event: eventId,
        user_identifier: userIdentifier,
        display_name: displayName,
        longitude: coords.value.lng,
        latitude: coords.value.lat,
        visibility: visibility.value,
        is_foreground: isForeground.value
      })
      lastPingTime.value = new Date()
    } catch (err: any) {
      // Non-fatal ping error
    }
  }

  /**
   * Updates privacy visibility scope and persists preference.
   */
  const setVisibility = (tier: VisibilityTier) => {
    visibility.value = tier
    localStorage.setItem('privacy_visibility', tier)
    if (coords.value && isForeground.value) {
      sendPing()
    }
  }

  /**
   * Handles visibility changes (pauses transmission on backgrounding).
   */
  const handleVisibilityChange = () => {
    isForeground.value = document.visibilityState === 'visible'
    if (isForeground.value) {
      sendPing()
    }
  }

  /**
   * Starts geolocation watch and periodic heartbeat.
   */
  const startTracking = () => {
    // Testing aid: a simulated position bypasses the browser's Geolocation API entirely.
    const simulated = readSimulatedPosition()
    if (simulated) {
      isSimulated.value = true
      isTracking.value = true
      error.value = null
      coords.value = { lat: simulated.lat, lng: simulated.lng }
      accuracy.value = 5
      if (isForeground.value) {
        sendPing()
      }
      heartbeatTimer = setInterval(() => {
        if (isForeground.value && isTracking.value) {
          sendPing()
        }
      }, 10000)
      return
    }

    if (!navigator.geolocation) {
      error.value = 'Geolocation is not supported by your browser.'
      return
    }

    isTracking.value = true
    error.value = null

    watchId = navigator.geolocation.watchPosition(
      (position) => {
        coords.value = {
          lat: position.coords.latitude,
          lng: position.coords.longitude
        }
        accuracy.value = position.coords.accuracy

        // Send initial ping upon acquiring coordinates
        if (isForeground.value) {
          sendPing()
        }
      },
      (err) => {
        error.value = `Geolocation error: ${err.message}`
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 5000
      }
    )

    // Heartbeat every 10 seconds while foregrounded
    heartbeatTimer = setInterval(() => {
      if (isForeground.value && isTracking.value) {
        sendPing()
      }
    }, 10000)
  }

  /**
   * Stops geolocation tracking and clears timer.
   */
  const stopTracking = () => {
    isTracking.value = false
    if (watchId !== null && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchId)
      watchId = null
    }
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  if (getCurrentInstance()) {
    onMounted(() => {
      document.addEventListener('visibilitychange', handleVisibilityChange)
      startTracking()
    })

    onUnmounted(() => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      stopTracking()
    })
  }

  return {
    coords,
    accuracy,
    isForeground,
    visibility,
    isTracking,
    isSimulated,
    error,
    lastPingTime,
    lastPing,
    userIdentifier,
    setVisibility,
    startTracking,
    stopTracking
  }
}
