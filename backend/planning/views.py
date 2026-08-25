from datetime import datetime, timezone

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import PlanningError
from .geocode import autocomplete
from .hos_planner import plan_trip
from .serializers import PlanRequestSerializer
from .types import DailyLog, DutySegment, Instruction, PlanResult


def _seg_dict(s: DutySegment) -> dict:
    return {
        "status": s.status,
        "start": s.start.isoformat(),
        "end": s.end.isoformat(),
        "miles": round(s.miles, 2),
        "location_label": s.location_label,
        "remark": s.remark,
        "stop_type": s.stop_type,
        "stationary": s.stationary,
        "lat": s.point.lat if s.point else None,
        "lng": s.point.lng if s.point else None,
    }


def _instruction_dict(i: Instruction) -> dict:
    return {
        "seq": i.seq,
        "action": i.action,
        "text": i.text,
        "start": i.start,
        "end": i.end,
        "status": i.status,
        "location_label": i.location_label,
        "miles": i.miles,
        "lat": i.lat,
        "lng": i.lng,
    }


def _log_dict(log: DailyLog) -> dict:
    return {
        "date": log.date,
        "from_location": log.from_location,
        "to_location": log.to_location,
        "total_miles_driving": log.total_miles_driving,
        "totals": log.totals,
        "remarks": [
            {"time": r.time, "location_label": r.location_label, "text": r.text}
            for r in log.remarks
        ],
        "recap": log.recap,
        "grid_segments": [
            {
                "status": g.status,
                "start_minute": g.start_minute,
                "end_minute": g.end_minute,
                "bracket": g.bracket,
            }
            for g in log.grid_segments
        ],
        "header": log.header,
    }


def serialize_plan(result: PlanResult) -> dict:
    return {
        "summary": result.summary,
        "places": result.places,
        "route": result.route,
        "instructions": [_instruction_dict(i) for i in result.instructions],
        "timeline": [_seg_dict(s) for s in result.timeline],
        "daily_logs": [_log_dict(d) for d in result.daily_logs],
        "assumptions": result.assumptions,
    }


class HealthView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        return Response(
            {
                "status": "ok",
                "time": datetime.now(timezone.utc).isoformat(),
                "service": "spotter-hos-api",
            }
        )


class AutocompleteView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        q = (request.query_params.get("q") or "").strip()
        try:
            results = autocomplete(q)
            return Response({"results": results})
        except PlanningError as exc:
            return Response(
                {
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "fields": exc.fields,
                    }
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )


class PlanView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        ser = PlanRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Invalid plan request",
                        "fields": ser.errors,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ser.validated_data
        try:
            result = plan_trip(
                current_location=data["current_location"],
                pickup_location=data["pickup_location"],
                dropoff_location=data["dropoff_location"],
                current_cycle_used_hours=data["current_cycle_used_hours"],
                start_datetime=data.get("start_datetime"),
            )
        except PlanningError as exc:
            http_status = {
                "VALIDATION_ERROR": status.HTTP_400_BAD_REQUEST,
                "GEOCODE_FAILED": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "ROUTE_FAILED": status.HTTP_502_BAD_GATEWAY,
                "PLAN_INTEGRITY_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
            }.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            return Response(
                {
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "fields": exc.fields,
                    }
                },
                status=http_status,
            )

        return Response(serialize_plan(result))
