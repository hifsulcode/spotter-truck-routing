import { useEffect, useMemo } from 'react'
import {
  CircleMarker,
  ImageOverlay,
  MapContainer,
  Pane,
  Polyline,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
} from 'react-leaflet'
import type { LatLngBoundsExpression } from 'leaflet'
import type { PlanResult, RouteOption } from '../lib/api'
import { splitByCheckpoints } from '../lib/geometry'
import { formatTime, riskColor } from '../lib/risk'

type Props = {
  plan: PlanResult | null
  selectedId: number
  onSelect: (id: number) => void
  heatUrl: string | null
  heatBounds: LatLngBoundsExpression | null
}

const US_CENTER: [number, number] = [39.5, -98.35]

function FitToPlan({ plan }: { plan: PlanResult | null }) {
  const map = useMap()
  useEffect(() => {
    if (!plan) return
    const { south, west, north, east } = plan.bbox
    // The side panel can change the map's size (mobile layout, window
    // resize); re-measure first so the fit uses the real container size.
    map.invalidateSize()
    map.fitBounds(
      [
        [south, west],
        [north, east],
      ],
      { padding: [24, 24] },
    )
  }, [plan, map])
  return null
}

function RouteLayer({
  route,
  selected,
  onSelect,
}: {
  route: RouteOption
  selected: boolean
  onSelect: (id: number) => void
}) {
  const segments = useMemo(
    () => splitByCheckpoints(route.geometry, route.checkpoints),
    [route.geometry, route.checkpoints],
  )
  const mid = route.geometry[Math.floor(route.geometry.length / 2)]
  const handlers = { click: () => onSelect(route.id) }

  return (
    <>
      {/* Dark casing under the selected route makes the colours readable. */}
      {selected && (
        <Polyline
          pane="casing"
          positions={route.geometry}
          pathOptions={{ color: '#0d1b2a', weight: 10, opacity: 0.55 }}
        />
      )}
      {segments.map((seg, i) => (
        <Polyline
          key={`${i}-${selected}`}
          pane={selected ? 'route-selected' : 'route-other'}
          positions={seg.positions}
          eventHandlers={handlers}
          pathOptions={{
            color: riskColor(seg.level),
            weight: selected ? 6 : 4,
            opacity: selected ? 1 : 0.5,
            dashArray: selected ? undefined : '6 8',
          }}
        />
      ))}
      {mid && (
        <CircleMarker center={mid} radius={1} pane="checkpoints-other" pathOptions={{ opacity: 0, fillOpacity: 0 }}>
          <Tooltip permanent direction="center" className="route-label">
            {route.name}
            {route.recommended ? ' ★' : ''}
          </Tooltip>
        </CircleMarker>
      )}
      {route.checkpoints.map((cp, i) => (
        <CircleMarker
          key={`${i}-${selected}`}
          pane={selected ? 'checkpoints-selected' : 'checkpoints-other'}
          center={[cp.lat, cp.lon]}
          radius={selected ? 5 : 3}
          eventHandlers={handlers}
          pathOptions={{
            color: '#fff',
            weight: 1.5,
            fillColor: riskColor(cp.risk.level),
            fillOpacity: selected ? 1 : 0.6,
          }}
        >
          <Popup>
            <strong>
              {route.name} · mile {cp.mile.toFixed(0)}
            </strong>
            <br />
            ETA {formatTime(cp.eta)} ({cp.hours_from_departure.toFixed(1)} h in)
            <br />
            Risk: <b style={{ color: riskColor(cp.risk.level) }}>{cp.risk.label}</b>
            <br />
            Wind {cp.weather.wind_mph.toFixed(0)} mph · Rain {cp.weather.rain_in_hr.toFixed(2)} in/h · Snow{' '}
            {cp.weather.snow_in_hr.toFixed(2)} in/h
            {cp.risk.reasons.length > 0 && (
              <>
                <br />
                <em>{cp.risk.reasons.join('; ')}</em>
              </>
            )}
          </Popup>
        </CircleMarker>
      ))}
    </>
  )
}

export default function MapView({ plan, selectedId, onSelect, heatUrl, heatBounds }: Props) {
  return (
    <MapContainer center={US_CENTER} zoom={4} preferCanvas style={{ height: '100%', width: '100%' }}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        maxZoom={19}
        className="base-tiles"
      />
      {heatUrl && heatBounds && (
        <ImageOverlay url={heatUrl} bounds={heatBounds} opacity={0.7} className="heat-overlay" zIndex={300} />
      )}
      {/* Fixed panes give a deterministic stacking order on the canvas:
          casing < other routes < selected route < checkpoints < endpoints.
          Leaflet can't move a layer between panes, so layers whose pane
          depends on selection are keyed on it and remount when it changes. */}
      <Pane name="casing" style={{ zIndex: 410 }} />
      <Pane name="route-other" style={{ zIndex: 420 }} />
      <Pane name="route-selected" style={{ zIndex: 430 }} />
      <Pane name="checkpoints-other" style={{ zIndex: 440 }} />
      <Pane name="checkpoints-selected" style={{ zIndex: 450 }} />
      <Pane name="endpoints" style={{ zIndex: 460 }} />
      {plan?.routes.map((route) => (
        <RouteLayer key={route.id} route={route} selected={route.id === selectedId} onSelect={onSelect} />
      ))}
      {plan && (
        <>
          <CircleMarker
            pane="endpoints"
            center={[plan.origin.lat, plan.origin.lon]}
            radius={9}
            pathOptions={{ color: '#fff', weight: 3, fillColor: '#1565c0', fillOpacity: 1 }}
          >
            <Tooltip direction="top">Origin: {plan.origin.label}</Tooltip>
          </CircleMarker>
          <CircleMarker
            pane="endpoints"
            center={[plan.destination.lat, plan.destination.lon]}
            radius={9}
            pathOptions={{ color: '#fff', weight: 3, fillColor: '#0d1b2a', fillOpacity: 1 }}
          >
            <Tooltip direction="top">Destination: {plan.destination.label}</Tooltip>
          </CircleMarker>
        </>
      )}
      <FitToPlan plan={plan} />
    </MapContainer>
  )
}
