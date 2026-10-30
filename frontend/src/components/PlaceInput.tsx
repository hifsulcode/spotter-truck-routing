import { Autocomplete, CircularProgress, TextField } from '@mui/material'
import { useEffect, useState } from 'react'
import { api, type Place } from '../lib/api'

type Props = {
  label: string
  value: Place | null
  onChange: (place: Place | null) => void
}

// Debounced place search; aborts stale requests so fast typing stays snappy.
export default function PlaceInput({ label, value, onChange }: Props) {
  const [input, setInput] = useState('')
  const [options, setOptions] = useState<Place[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (input.trim().length < 2 || input === value?.label) return
    const ctrl = new AbortController()
    const timer = setTimeout(async () => {
      setLoading(true)
      try {
        const { results } = await api.geocode(input, ctrl.signal)
        setOptions(results)
      } catch {
        /* aborted or offline: keep previous options */
      } finally {
        setLoading(false)
      }
    }, 300)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
  }, [input, value?.label])

  return (
    <Autocomplete
      value={value}
      onChange={(_, place) => onChange(place)}
      inputValue={input}
      onInputChange={(_, text) => setInput(text)}
      options={options}
      filterOptions={(x) => x}
      // Tab/blur keeps the top match instead of silently clearing the field.
      autoHighlight
      autoSelect
      getOptionLabel={(o) => o.label}
      getOptionKey={(o) => `${o.lat},${o.lon}`}
      isOptionEqualToValue={(a, b) => a.lat === b.lat && a.lon === b.lon}
      noOptionsText={input.length < 2 ? 'Type a city or address' : 'No matches'}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          size="small"
          required
          slotProps={{
            input: {
              ...params.InputProps,
              endAdornment: (
                <>
                  {loading ? <CircularProgress size={16} /> : null}
                  {params.InputProps.endAdornment}
                </>
              ),
            },
          }}
        />
      )}
    />
  )
}
