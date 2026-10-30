// One palette for routes, checkpoints, chips and the heatmap legend.

export const RISK_LEVELS = ['Low', 'Moderate', 'High', 'Severe', 'No Travel'] as const

export const RISK_COLORS = ['#2e7d32', '#f9a825', '#ef6c00', '#c62828', '#6a1b9a']

// RGBA used to paint heatmap cells. Low is transparent so calm areas don't
// tint the map; each step up gets more opaque.
export const HEAT_RGBA: [number, number, number, number][] = [
  [46, 125, 50, 0],
  [249, 168, 37, 120],
  [239, 108, 0, 160],
  [198, 40, 40, 190],
  [106, 27, 154, 210],
]

export const riskColor = (level: number) => RISK_COLORS[Math.max(0, Math.min(4, level))]

export function formatDuration(seconds: number) {
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return h ? `${h} h ${m} min` : `${m} min`
}

export function formatTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
  })
}
