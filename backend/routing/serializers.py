from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

# Open-Meteo forecasts run 16 days out; keep the trip window inside that.
MAX_DAYS_AHEAD = 14


class PlaceField(serializers.Field):
    """Either free text ("Dallas, TX") or {"label", "lat", "lon"}."""

    def to_internal_value(self, data):
        if isinstance(data, str):
            if not data.strip():
                raise serializers.ValidationError("Enter a place.")
            return data.strip()
        if isinstance(data, dict):
            try:
                lat, lon = float(data["lat"]), float(data["lon"])
            except (KeyError, TypeError, ValueError):
                raise serializers.ValidationError("Place needs numeric lat and lon.")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise serializers.ValidationError("Coordinates out of range.")
            return {"label": str(data.get("label", "")), "lat": lat, "lon": lon}
        raise serializers.ValidationError("Place must be text or {lat, lon}.")

    def to_representation(self, value):
        return value


def _validate_departure(value):
    now = timezone.now()
    if value < now - timedelta(hours=6):
        raise serializers.ValidationError("Departure can't be more than 6 hours in the past.")
    if value > now + timedelta(days=MAX_DAYS_AHEAD):
        raise serializers.ValidationError(
            f"Forecasts only reach {MAX_DAYS_AHEAD} days ahead; pick an earlier departure."
        )
    return value


class PlanSerializer(serializers.Serializer):
    origin = PlaceField()
    destination = PlaceField()
    departure = serializers.DateTimeField(validators=[_validate_departure])
    load_lbs = serializers.FloatField(min_value=0, max_value=200_000)
    interval_mi = serializers.ChoiceField(choices=[10, 25, 50], default=25)


class HeatmapSerializer(serializers.Serializer):
    south = serializers.FloatField(min_value=-90, max_value=90)
    west = serializers.FloatField(min_value=-180, max_value=180)
    north = serializers.FloatField(min_value=-90, max_value=90)
    east = serializers.FloatField(min_value=-180, max_value=180)
    start = serializers.DateTimeField(validators=[_validate_departure])
    load_lbs = serializers.FloatField(min_value=0, max_value=200_000)
    grid = serializers.IntegerField(min_value=4, max_value=24, default=14)

    def validate(self, attrs):
        if attrs["north"] <= attrs["south"] or attrs["east"] <= attrs["west"]:
            raise serializers.ValidationError("Bounding box is inverted.")
        if (attrs["north"] - attrs["south"]) > 40 or (attrs["east"] - attrs["west"]) > 60:
            raise serializers.ValidationError("Bounding box is too large.")
        return attrs
