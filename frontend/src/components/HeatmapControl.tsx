import { Box, FormControlLabel, IconButton, Paper, Slider, Stack, Switch, Typography } from '@mui/material'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import PauseIcon from '@mui/icons-material/Pause'
import { useEffect } from 'react'
import { RISK_COLORS, RISK_LEVELS } from '../lib/risk'

type Props = {
  hours: string[]
  hour: number
  onHour: (h: number) => void
  playing: boolean
  onPlaying: (p: boolean) => void
  visible: boolean
  onVisible: (v: boolean) => void
  loading: boolean
}

export default function HeatmapControl({
  hours,
  hour,
  onHour,
  playing,
  onPlaying,
  visible,
  onVisible,
  loading,
}: Props) {
  const max = Math.max(0, hours.length - 1)

  // Animate through the forecast; frames are pre-rendered so this is cheap.
  useEffect(() => {
    if (!playing || !max) return
    const id = window.setInterval(() => onHour(hour >= max ? 0 : hour + 1), 450)
    return () => window.clearInterval(id)
  }, [playing, hour, max, onHour])

  const label = hours[hour]
    ? new Date(hours[hour]).toLocaleString(undefined, { weekday: 'short', hour: 'numeric' })
    : '—'

  return (
    <Paper
      elevation={4}
      sx={{ position: 'absolute', left: 16, right: 16, bottom: 20, zIndex: 1000, px: 2, py: 1, maxWidth: 720, mx: 'auto' }}
    >
      <Stack direction="row" alignItems="center" spacing={1.5}>
        <IconButton size="small" onClick={() => onPlaying(!playing)} disabled={!max || !visible}>
          {playing ? <PauseIcon /> : <PlayArrowIcon />}
        </IconButton>
        <Box flex={1} px={1}>
          <Typography variant="caption" color="text.secondary">
            {loading ? 'Loading 48 h corridor forecast…' : `Weather risk at +${hour} h · ${label}`}
          </Typography>
          <Slider
            size="small"
            min={0}
            max={max || 48}
            step={1}
            value={hour}
            disabled={!max || !visible}
            onChange={(_, v) => {
              onPlaying(false)
              onHour(v as number)
            }}
            marks={[0, 12, 24, 36, 48].map((v) => ({ value: v, label: `${v}h` }))}
          />
        </Box>
        <Stack spacing={0.25} sx={{ display: { xs: 'none', sm: 'flex' } }}>
          {RISK_LEVELS.slice(1).map((name, i) => (
            <Stack key={name} direction="row" alignItems="center" spacing={0.75}>
              <Box sx={{ width: 10, height: 10, borderRadius: 0.5, bgcolor: RISK_COLORS[i + 1] }} />
              <Typography variant="caption" lineHeight={1.1}>
                {name}
              </Typography>
            </Stack>
          ))}
        </Stack>
        <FormControlLabel
          control={<Switch size="small" checked={visible} onChange={(e) => onVisible(e.target.checked)} />}
          label={<Typography variant="caption">Heatmap</Typography>}
        />
      </Stack>
    </Paper>
  )
}
