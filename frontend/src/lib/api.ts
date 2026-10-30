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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  const body = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    throw new Error(formatError(body) || `Request failed (${resp.status})`)
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

export const api = {
  geocode: (q: string, signal?: AbortSignal) =>
    request<{ results: Place[] }>(`/api/v1/geocode/?q=${encodeURIComponent(q)}`, { signal }),
  plan: (body: PlanRequest) =>
    request<PlanResult>('/api/v1/plan/', { method: 'POST', body: JSON.stringify(body) }),
  heatmap: (bbox: PlanResult['bbox'], start: string, loadLbs: number) =>
    request<HeatmapResult>('/api/v1/heatmap/', {
      method: 'POST',
      body: JSON.stringify({ ...bbox, start, load_lbs: loadLbs, grid: 16 }),
    }),
}
