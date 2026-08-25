from rest_framework import serializers


class StrictFloatField(serializers.FloatField):
    """Reject bools — JSON true/false must not coerce to 1.0/0.0."""

    def to_internal_value(self, data):
        if isinstance(data, bool):
            self.fail("invalid")
        return super().to_internal_value(data)


class PlanRequestSerializer(serializers.Serializer):
    current_location = serializers.CharField(max_length=200)
    pickup_location = serializers.CharField(max_length=200)
    dropoff_location = serializers.CharField(max_length=200)
    current_cycle_used_hours = StrictFloatField(min_value=0, max_value=70)
    start_datetime = serializers.DateTimeField(required=False, allow_null=True)
