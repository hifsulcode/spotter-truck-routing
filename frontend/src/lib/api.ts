// Typed client for the Django API.

const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

export type Place = { label: string; lat: number; lon: number }

export type RiskInfo = {
  level: number // 0 Low .. 4 No Travel
  label: string
  wind: string
  rain: string
  snow: string
  reasons: string[]
}

export type Checkpoint = {
  lat: number
  lon: number
  mile: number
  segment_miles: number
  eta: string
  hours_from_departure: number
  weather: { wind_mph: number; rain_in_hr: number; snow_in_hr: number }
  risk: RiskInfo
}

export type RouteSummary = {
  miles_by_level: Record<string, number>
  no_travel_miles: number
  severe_miles: number
  high_miles: number
  average_risk: number
  worst_level: number
  worst_label: string
}

export type RouteOption = {
  id: number
  name: string
  source: string
  distance_mi: number
  duration_s: number
  arrival: string
  geometry: [number, number][]
  checkpoints: Checkpoint[]
  summary: RouteSummary
  rank: number
  recommended: boolean
}

export type PlanResult = {
  origin: Place
  destination: Place
  departure: string
  load_lbs: number
  interval_mi: number
  recommended_route_id: number
  recommendation: string
  bbox: { south: number; west: number; north: number; east: number }
  routes: RouteOption[]
}

export type HeatmapResult = {
  grid_size: number
  points: [number, number][]
  hours: string[]
  levels: number[][] // [hour][point]
  wind_mph: number[][]
}

export type PlanRequest = {
  origin: Place | string
  destination: Place | string
  departure: string
  load_lbs: number
  interval_mi: 10 | 25 | 50
}

export class ApiError extends Error {
  status: number
  body: Record<string, unknown>

  constructor(message: string, status: number, body: Record<string, unknown>) {
    super(message)
    this.status = status
    this.body = body
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  const body = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    throw new ApiError(formatError(body) || `Request failed (${resp.status})`, resp.status, body)
  }
  return body as T
}

// DRF errors come back as {field: [msg]} or {detail: msg}; flatten for display.
function formatError(body: unknown): string {
  if (!body || typeof body !== 'object') return ''
  const record = body as Record<string, unknown>
  if (typeof record.detail === 'string') return record.detail
  return Object.entries(record)
    .map(([field, msgs]) => `${field}: ${Array.isArray(msgs) ? msgs.join(' ') : String(msgs)}`)
    .join(' · ')
}

// The API fetches weather and places itself. On free hosting its outbound IP is
// shared with other apps, so a free provider can refuse it (Open-Meteo's daily
// per-IP quota, Photon blocks). The API then replies 503 `weather_unavailable`
// with the exact Open-Meteo requests; the browser runs them from the viewer's
// own IP and posts the answers back. Risk scoring and ranking stay on the API.

type WeatherRequest = { url: string; params: Record<string, string> }

const forecastCache = new Map<string, Promise<unknown>>()

function fetchForecast({ url, params }: WeatherRequest): Promise<unknown> {
  const key = `${url}?${new URLSearchParams(params)}`
  let pending = forecastCache.get(key)
  if (!pending) {
    pending = fetch(key).then(async (resp) => {
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(`Weather provider: ${data.reason ?? `HTTP ${resp.status}`}`)
      return data
    })
    pending.catch(() => forecastCache.delete(key))
    forecastCache.set(key, pending)
  }
  return pending
}

async function postWithWeather<T>(path: string, body: object): Promise<T> {
  try {
    return await request<T>(path, { method: 'POST', body: JSON.stringify(body) })
  } catch (e) {
    if (!(e instanceof ApiError) || e.body.code !== 'weather_unavailable') throw e
    const weather = await Promise.all((e.body.weather_requests as WeatherRequest[]).map(fetchForecast))
    return request<T>(path, { method: 'POST', body: JSON.stringify({ ...body, weather }) })
  }
}

const PHOTON_URL = 'https://photon.komoot.io/api/'
let geocodeInBrowser = false // set once the API reports Photon refused it

// Same labels and de-duplication as the API's geocoder.
async function photonSearch(q: string, signal?: AbortSignal): Promise<{ results: Place[] }> {
  const resp = await fetch(`${PHOTON_URL}?${new URLSearchParams({ q, limit: '6', lang: 'en' })}`, { signal })
  if (!resp.ok) throw new Error(`Place search failed (HTTP ${resp.status})`)
  const data = await resp.json()
  const seen = new Set<string>()
  const results: Place[] = []
  for (const feature of data.features ?? []) {
    const p = feature.properties ?? {}
    const label = [...new Set([p.name, p.city, p.state, p.country].filter(Boolean))].join(', ')
    if (!label || seen.has(label)) continue
    seen.add(label)
    const [lon, lat] = feature.geometry.coordinates
    results.push({ label, lat, lon })
  }
  return { results }
}

export const api = {
  geocode: async (q: string, signal?: AbortSignal) => {
    if (!geocodeInBrowser) {
      try {
        return await request<{ results: Place[] }>(`/api/v1/geocode/?q=${encodeURIComponent(q)}`, { signal })
      } catch (e) {
        if (!(e instanceof ApiError) || e.status < 500) throw e
        geocodeInBrowser = true
      }
    }
    return photonSearch(q, signal)
  },
  plan: (body: PlanRequest) => postWithWeather<PlanResult>('/api/v1/plan/', body),
  heatmap: (bbox: PlanResult['bbox'], start: string, loadLbs: number) =>
    postWithWeather<HeatmapResult>('/api/v1/heatmap/', { ...bbox, start, load_lbs: loadLbs, grid: 16 }),
}
