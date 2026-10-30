import {
  Button,
  InputAdornment,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import RouteIcon from '@mui/icons-material/AltRoute'
import { useState, type FormEvent } from 'react'
import type { Place, PlanRequest } from '../lib/api'
import PlaceInput from './PlaceInput'

// <input type="datetime-local"> wants local time without a zone.
function toLocalInput(date: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function nextHour() {
  const d = new Date()
  d.setMinutes(0, 0, 0)
  d.setHours(d.getHours() + 1)
  return d
}

type Props = { loading: boolean; onSubmit: (req: PlanRequest) => void }

export default function TripForm({ loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | null>(null)
  const [destination, setDestination] = useState<Place | null>(null)
  const [departure, setDeparture] = useState(toLocalInput(nextHour()))
  const [load, setLoad] = useState('42000')
  const [intervalMi, setIntervalMi] = useState<10 | 25 | 50>(25)

  const loadLbs = Number(load)
  const valid = origin && destination && departure && Number.isFinite(loadLbs) && loadLbs >= 0

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!valid) return
    onSubmit({
      origin,
      destination,
      departure: new Date(departure).toISOString(),
      load_lbs: loadLbs,
      interval_mi: intervalMi,
    })
  }

  return (
    <Stack component="form" spacing={1.5} onSubmit={submit}>
      <PlaceInput label="Origin" value={origin} onChange={setOrigin} />
      <PlaceInput label="Destination" value={destination} onChange={setDestination} />
      <Stack direction="row" spacing={1}>
        <TextField
          label="Departure"
          type="datetime-local"
          size="small"
          value={departure}
          onChange={(e) => setDeparture(e.target.value)}
          slotProps={{ inputLabel: { shrink: true } }}
          sx={{ flex: 1.4 }}
          required
        />
        <TextField
          label="Load weight"
          type="number"
          size="small"
          value={load}
          onChange={(e) => setLoad(e.target.value)}
          slotProps={{
            input: { endAdornment: <InputAdornment position="end">lb</InputAdornment> },
            htmlInput: { min: 0, max: 200000, step: 500 },
          }}
          sx={{ flex: 1 }}
          required
        />
      </Stack>
      <Stack direction="row" alignItems="center" spacing={1.5}>
        <Typography variant="body2" color="text.secondary">
          Weather every
        </Typography>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={intervalMi}
          onChange={(_, v) => v && setIntervalMi(v)}
        >
          {[10, 25, 50].map((mi) => (
            <ToggleButton key={mi} value={mi} sx={{ px: 1.5 }}>
              {mi} mi
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Stack>
      <Button
        type="submit"
        variant="contained"
        startIcon={<RouteIcon />}
        disabled={!valid || loading}
      >
        {loading ? 'Checking routes and weather…' : 'Find safest route'}
      </Button>
    </Stack>
  )
}
