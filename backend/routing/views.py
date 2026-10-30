import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import heatmap, planner
from .serializers import HeatmapSerializer, PlanSerializer
from .services import geocode
from .services.http import UpstreamError
from .services.weather import SuppliedWeatherError, WeatherUnavailable

log = logging.getLogger(__name__)


def upstream_failure(exc):
    log.warning("Upstream failure: %s", exc)
    return Response(
        {"detail": f"A data provider failed: {exc}. Please try again."},
        status=status.HTTP_502_BAD_GATEWAY,
    )


def weather_unavailable(exc):
    """Hand the forecast requests to the client to run from its own IP."""
    log.warning("Weather unavailable on the server, asking the client: %s", exc)
    return Response(
        {
            "code": "weather_unavailable",
            "detail": "The weather provider refused this server. Fetch these forecasts "
            "and send them back as `weather`.",
            "weather_requests": exc.requests,
        },
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def bad_weather(exc):
    return Response(
        {"weather": [f"Supplied forecasts don't match this request: {exc}."]},
        status=status.HTTP_400_BAD_REQUEST,
    )


class HealthView(APIView):
    def get(self, request):
        return Response({"status": "ok"})


class GeocodeView(APIView):
    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if len(query) < 2:
            return Response({"results": []})
        try:
            return Response({"results": geocode.search(query)})
        except UpstreamError as exc:
            return upstream_failure(exc)


class PlanView(APIView):
    """POST a trip, get back three ranked routes with checkpoint risk."""

    def post(self, request):
        ser = PlanSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        try:
            origin = geocode.resolve(data["origin"])
            destination = geocode.resolve(data["destination"])
            result = planner.plan_trip(
                origin,
                destination,
                data["departure"],
                data["load_lbs"],
                int(data["interval_mi"]),
                supplied_weather=data.get("weather"),
            )
        except WeatherUnavailable as exc:
            return weather_unavailable(exc)
        except SuppliedWeatherError as exc:
            return bad_weather(exc)
        except UpstreamError as exc:
            return upstream_failure(exc)
        return Response(result)


class HeatmapView(APIView):
    """POST a bounding box + start time, get 49 hourly risk frames."""

    def post(self, request):
        ser = HeatmapSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            result = heatmap.build(
                d["south"], d["west"], d["north"], d["east"], d["start"], d["load_lbs"], d["grid"],
                supplied_weather=d.get("weather"),
            )
        except WeatherUnavailable as exc:
            return weather_unavailable(exc)
        except SuppliedWeatherError as exc:
            return bad_weather(exc)
        except UpstreamError as exc:
            return upstream_failure(exc)
        return Response(result)
