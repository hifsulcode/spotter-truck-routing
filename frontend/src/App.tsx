import { Alert, Box, Divider, LinearProgress, Paper, Stack, Typography } from '@mui/material'
import LocalShippingIcon from '@mui/icons-material/LocalShipping'
import { useCallback, useMemo, useState } from 'react'
import type { LatLngBoundsExpression } from 'leaflet'
import HeatmapControl from './components/HeatmapControl'
import MapView from './components/MapView'
import RouteCards from './components/RouteCards'
import TripForm from './components/TripForm'
import { api, type HeatmapResult, type PlanRequest, type PlanResult } from './lib/api'
import { heatBounds, renderHeatFrames } from './lib/geometry'

export default function App() {
  const [plan, setPlan] = useState<PlanResult | null>(null)
  const [selectedId, setSelectedId] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [heat, setHeat] = useState<HeatmapResult | null>(null)
  const [heatLoading, setHeatLoading] = useState(false)
  const [hour, setHour] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [heatVisible, setHeatVisible] = useState(true)

  const handlePlan = useCallback(async (req: PlanRequest) => {
    setLoading(true)
    setError(null)
    setPlaying(false)
    try {
      const result = await api.plan(req)
      setPlan(result)
      setSelectedId(result.recommended_route_id)
      setHeat(null)
      setHour(0)
      // Routes first, heatmap second: the user sees the answer without waiting
      // for the 48 h corridor forecast.
      setHeatLoading(true)
      api
        .heatmap(result.bbox, result.departure, result.load_lbs)
        .then(setHeat)
        .catch((e: Error) => setError(`Heatmap unavailable: ${e.message}`))
        .finally(() => setHeatLoading(false))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  // Each forecast hour becomes a data URL once; the slider just picks one.
  const frames = useMemo(() => (heat ? renderHeatFrames(heat) : []), [heat])
  const bounds = useMemo<LatLngBoundsExpression | null>(() => (heat ? heatBounds(heat) : null), [heat])
  const heatUrl = heatVisible && frames.length ? frames[Math.min(hour, frames.length - 1)] : null

  return (
    <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, height: '100vh' }}>
      <Paper
        square
        elevation={2}
        sx={{
          width: { xs: '100%', md: 400 },
          maxHeight: { xs: '55vh', md: '100vh' },
          overflowY: 'auto',
          p: 2,
          zIndex: 2,
        }}
      >
        <Stack direction="row" alignItems="center" spacing={1} mb={0.5}>
          <LocalShippingIcon color="primary" />
          <Typography variant="h6" fontWeight={700}>
            Weather-Aware Truck Routing
          </Typography>
        </Stack>
        <Typography variant="body2" color="text.secondary" mb={2}>
          Compares three routes using the forecast at the time your truck reaches each checkpoint.
        </Typography>

        <TripForm loading={loading} onSubmit={handlePlan} />
        {loading && <LinearProgress sx={{ mt: 1.5 }} />}
        {error && (
          <Alert severity="error" sx={{ mt: 1.5 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {plan && (
          <>
            <Divider sx={{ my: 2 }} />
            <Alert severity="info" icon={false} sx={{ mb: 1.5 }}>
              {plan.recommendation}
            </Alert>
            <RouteCards routes={plan.routes} selectedId={selectedId} onSelect={setSelectedId} />
            <Typography variant="caption" color="text.secondary" display="block" mt={1.5}>
              Ranking: fewest No Travel → Severe → High miles, then lowest average risk, then
              shortest time. Weather sampled every {plan.interval_mi} mi.
            </Typography>
          </>
        )}
      </Paper>

      <Box sx={{ position: 'relative', flex: 1, minHeight: 360 }}>
        <MapView
          plan={plan}
          selectedId={selectedId}
          onSelect={setSelectedId}
          heatUrl={heatUrl}
          heatBounds={bounds}
        />
        {plan && (
          <HeatmapControl
            hours={heat?.hours ?? []}
            hour={hour}
            onHour={setHour}
            playing={playing}
            onPlaying={setPlaying}
            visible={heatVisible}
            onVisible={setHeatVisible}
            loading={heatLoading}
          />
        )}
      </Box>
    </Box>
  )
}
