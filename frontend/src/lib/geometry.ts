import type { Checkpoint, HeatmapResult } from './api'
import { HEAT_RGBA } from './risk'

type LatLng = [number, number]

const R_MI = 3958.7613
const toRad = (d: number) => (d * Math.PI) / 180

function haversine(a: LatLng, b: LatLng) {
  const dLat = toRad(b[0] - a[0])
  const dLon = toRad(b[1] - a[1])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLon / 2) ** 2
  return 2 * R_MI * Math.asin(Math.min(1, Math.sqrt(h)))
}

export type RiskSegment = { positions: LatLng[]; level: number }

/**
 * Cut a route polyline at its checkpoints so each stretch can be coloured by
 * the risk of the checkpoint that ends it (the same miles the backend counts).
 * The polyline is thinned server-side, so miles are re-measured here and
 * scaled to the checkpoint mileage.
 */
export function splitByCheckpoints(geometry: LatLng[], checkpoints: Checkpoint[]): RiskSegment[] {
  if (geometry.length < 2 || checkpoints.length < 2) return [{ positions: geometry, level: 0 }]

  const cum = [0]
  for (let i = 1; i < geometry.length; i++) cum.push(cum[i - 1] + haversine(geometry[i - 1], geometry[i]))
  const scale = checkpoints[checkpoints.length - 1].mile / (cum[cum.length - 1] || 1)

  const segments: RiskSegment[] = []
  let v = 0
  for (let c = 1; c < checkpoints.length; c++) {
    const endMile = checkpoints[c].mile
    const positions: LatLng[] = [[checkpoints[c - 1].lat, checkpoints[c - 1].lon]]
    while (v < geometry.length && cum[v] * scale < endMile) {
      positions.push(geometry[v])
      v++
    }
    positions.push([checkpoints[c].lat, checkpoints[c].lon])
    const level = checkpoints[c].risk.level
    const prev = segments[segments.length - 1]
    // Merge neighbours with the same level: fewer polylines, smoother panning.
    if (prev && prev.level === level) prev.positions.push(...positions.slice(1))
    else segments.push({ positions, level })
  }
  return segments
}

/**
 * Pre-render every forecast hour to a tiny PNG (one pixel per grid point).
 * Leaflet stretches it over the corridor and the browser's bilinear scaling
 * turns the grid into a smooth heatmap. Moving the slider only swaps an
 * image URL, so it stays at 60 fps regardless of grid size.
 */
export function renderHeatFrames(heat: HeatmapResult): string[] {
  const n = heat.grid_size
  const canvas = document.createElement('canvas')
  canvas.width = n
  canvas.height = n
  const ctx = canvas.getContext('2d')
  if (!ctx) return []

  return heat.levels.map((levels) => {
    const img = ctx.createImageData(n, n)
    for (let i = 0; i < levels.length; i++) {
      // Backend rows go south -> north; image rows go top (north) -> down.
      const row = Math.floor(i / n)
      const col = i % n
      const px = ((n - 1 - row) * n + col) * 4
      const [r, g, b, a] = HEAT_RGBA[levels[i]] ?? HEAT_RGBA[0]
      img.data[px] = r
      img.data[px + 1] = g
      img.data[px + 2] = b
      img.data[px + 3] = a
    }
    ctx.putImageData(img, 0, 0)
    return canvas.toDataURL('image/png')
  })
}

/** Bounds of the grid cells (half a cell beyond the outer sample points). */
export function heatBounds(heat: HeatmapResult): [LatLng, LatLng] {
  const lats = heat.points.map((p) => p[0])
  const lons = heat.points.map((p) => p[1])
  const n = heat.grid_size
  const s = Math.min(...lats)
  const nth = Math.max(...lats)
  const w = Math.min(...lons)
  const e = Math.max(...lons)
  const halfLat = (nth - s) / (n - 1) / 2
  const halfLon = (e - w) / (n - 1) / 2
  return [
    [s - halfLat, w - halfLon],
    [nth + halfLat, e + halfLon],
  ]
}
