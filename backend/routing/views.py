import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import heatmap, planner
from .serializers import HeatmapSerializer, PlanSerializer
from .services import geocode
from .services.http import UpstreamError

log = logging.getLogger(__name__)


def upstream_failure(exc):
    log.warning("Upstream failure: %s", exc)
    return Response(
        {"detail": f"A data provider failed: {exc}. Please try again."},
        status=status.HTTP_502_BAD_GATEWAY,
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
            )
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
                d["south"], d["west"], d["north"], d["east"], d["start"], d["load_lbs"], d["grid"]
            )
        except UpstreamError as exc:
            return upstream_failure(exc)
        return Response(result)
