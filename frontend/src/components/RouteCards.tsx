import { Box, Card, CardActionArea, Chip, Stack, Tooltip, Typography } from '@mui/material'
import StarIcon from '@mui/icons-material/Star'
import type { RouteOption } from '../lib/api'
import { RISK_COLORS, RISK_LEVELS, formatDuration, formatTime, riskColor } from '../lib/risk'

type Props = {
  routes: RouteOption[]
  selectedId: number
  onSelect: (id: number) => void
}

// Stacked bar showing how many miles of the route fall in each risk level.
function RiskBar({ route }: { route: RouteOption }) {
  const total = Object.values(route.summary.miles_by_level).reduce((a, b) => a + b, 0) || 1
  return (
    <Box sx={{ display: 'flex', height: 8, borderRadius: 1, overflow: 'hidden', bgcolor: 'grey.200' }}>
      {RISK_LEVELS.map((label, i) => {
        const miles = route.summary.miles_by_level[label] ?? 0
        if (!miles) return null
        return (
          <Tooltip key={label} title={`${label}: ${miles.toFixed(0)} mi`}>
            <Box sx={{ width: `${(miles / total) * 100}%`, bgcolor: RISK_COLORS[i] }} />
          </Tooltip>
        )
      })}
    </Box>
  )
}

export default function RouteCards({ routes, selectedId, onSelect }: Props) {
  const ordered = [...routes].sort((a, b) => a.rank - b.rank)
  return (
    <Stack spacing={1}>
      {ordered.map((route) => {
        const s = route.summary
        const selected = route.id === selectedId
        return (
          <Card
            key={route.id}
            variant="outlined"
            sx={{
              borderColor: selected ? 'primary.main' : 'divider',
              borderWidth: selected ? 2 : 1,
            }}
          >
            <CardActionArea onClick={() => onSelect(route.id)} sx={{ p: 1.5 }}>
              <Stack direction="row" alignItems="center" spacing={1} mb={0.5}>
                <Typography fontWeight={700}>{route.name}</Typography>
                {route.recommended && (
                  <Chip icon={<StarIcon />} label="Recommended" color="primary" size="small" />
                )}
                <Box flex={1} />
                <Chip
                  label={s.worst_label}
                  size="small"
                  sx={{ bgcolor: riskColor(s.worst_level), color: '#fff', fontWeight: 600 }}
                />
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {route.distance_mi.toFixed(0)} mi · {formatDuration(route.duration_s)} · arrives{' '}
                {formatTime(route.arrival)}
              </Typography>
              <Box my={1}>
                <RiskBar route={route} />
              </Box>
              <Stack direction="row" spacing={1.5} flexWrap="wrap">
                {s.no_travel_miles > 0 && (
                  <Typography variant="caption" color={RISK_COLORS[4]}>
                    No Travel <b>{s.no_travel_miles.toFixed(0)} mi</b>
                  </Typography>
                )}
                <Typography variant="caption">
                  Severe <b>{s.severe_miles.toFixed(0)} mi</b>
                </Typography>
                <Typography variant="caption">
                  High <b>{s.high_miles.toFixed(0)} mi</b>
                </Typography>
                <Typography variant="caption">
                  Avg risk <b>{s.average_risk.toFixed(2)}</b> / 4
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {route.checkpoints.length} checkpoints
                </Typography>
              </Stack>
            </CardActionArea>
          </Card>
        )
      })}
    </Stack>
  )
}
