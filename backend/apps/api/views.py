from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.ingestion.models import SourceFile
from apps.records.models import ActivityRecord, RecordRevision
from apps.ingestion.service import ingest_sap, ingest_utility, ingest_travel
from .serializers import (
    UserMeSerializer,
    SourceFileSerializer,
    ActivityRecordListSerializer,
    ActivityRecordLineageSerializer,
    ActivityRecordUpdateSerializer,
    RecordRevisionSerializer,
    EmissionCalculationSerializer,
)


# ---- Auth -------------------------------------------------------------------

class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserMeSerializer(request.user).data)


# ---- Source Files -----------------------------------------------------------

class SourceFileListView(generics.ListAPIView):
    serializer_class = SourceFileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SourceFile.objects.for_org(self.request.user.organization)


class SourceFileDetailView(generics.RetrieveAPIView):
    serializer_class = SourceFileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SourceFile.objects.for_org(self.request.user.organization)


# ---- Ingestion --------------------------------------------------------------

class IngestSAPView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "No file provided."}, status=400)

        content = file_obj.read()
        result = ingest_sap(
            content=content,
            filename=file_obj.name,
            org=request.user.organization,
            user=request.user,
        )
        code = 200 if result.get("already_ingested") else 201
        return Response(result, status=code)


class IngestUtilityView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "No file provided."}, status=400)

        content = file_obj.read()
        result = ingest_utility(
            content=content,
            filename=file_obj.name,
            org=request.user.organization,
            user=request.user,
        )
        code = 200 if result.get("already_ingested") else 201
        return Response(result, status=code)


class IngestTravelView(APIView):
    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payload = request.data
        if not payload:
            return Response({"error": "No JSON payload provided."}, status=400)

        report_name = payload.get("report_id", payload.get("report_name", "travel_report"))
        result = ingest_travel(
            payload=payload,
            report_name=str(report_name),
            org=request.user.organization,
            user=request.user,
        )
        code = 200 if result.get("already_ingested") else 201
        return Response(result, status=code)


# ---- Activity Records -------------------------------------------------------

class ActivityRecordListView(generics.ListAPIView):
    serializer_class = ActivityRecordListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ActivityRecord.objects.for_org(self.request.user.organization)
        params = self.request.query_params

        state = params.get("state")
        if state:
            qs = qs.filter(state=state)

        quality_tier = params.get("quality_tier")
        if quality_tier:
            qs = qs.filter(quality_tier=quality_tier)

        source_type = params.get("source_type")
        if source_type:
            qs = qs.filter(source_row__source_file__source_type=source_type)

        date_from = params.get("date_from")
        if date_from:
            qs = qs.filter(activity_date__gte=date_from)

        date_to = params.get("date_to")
        if date_to:
            qs = qs.filter(activity_date__lte=date_to)

        source_file_id = params.get("source_file_id")
        if source_file_id:
            qs = qs.filter(source_row__source_file_id=source_file_id)

        return qs.select_related(
            "source_row__source_file", "reviewed_by", "locked_by"
        ).prefetch_related("calculations")


class ActivityRecordDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return ActivityRecordUpdateSerializer
        return ActivityRecordLineageSerializer

    def get_queryset(self):
        return ActivityRecord.objects.for_org(self.request.user.organization).select_related(
            "source_row__source_file", "reviewed_by", "locked_by"
        ).prefetch_related("calculations__emission_factor")

    def perform_update(self, serializer):
        instance = serializer.instance
        # Attach context for audit signal
        instance._changed_by = self.request.user
        instance._change_reason = self.request.data.get("change_reason", "")
        serializer.save()

        # Recalculate emission after quantity change
        from apps.ingestion.service import create_emission_calculation
        instance.calculations.filter(is_current=True).update(is_current=False)
        create_emission_calculation(instance, user=self.request.user)


class ActivityRecordLineageView(generics.RetrieveAPIView):
    serializer_class = ActivityRecordLineageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ActivityRecord.objects.for_org(self.request.user.organization).select_related(
            "source_row__source_file", "reviewed_by", "locked_by"
        ).prefetch_related("calculations__emission_factor")


class ActivityRecordRevisionsView(generics.ListAPIView):
    serializer_class = RecordRevisionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        record_id = self.kwargs["pk"]
        # Verify org access
        record = ActivityRecord.objects.for_org(self.request.user.organization).filter(pk=record_id).first()
        if not record:
            return RecordRevision.objects.none()
        return RecordRevision.objects.filter(activity_record=record)


class ActivityRecordCalculationsView(generics.ListAPIView):
    serializer_class = EmissionCalculationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        record_id = self.kwargs["pk"]
        record = ActivityRecord.objects.for_org(self.request.user.organization).filter(pk=record_id).first()
        if not record:
            from apps.emissions.models import EmissionCalculation
            return EmissionCalculation.objects.none()
        return record.calculations.select_related("emission_factor").order_by("-calculated_at")


# ---- Bulk Actions -----------------------------------------------------------

class BulkApproveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        record_ids = request.data.get("record_ids", [])
        if not record_ids:
            return Response({"error": "record_ids is required."}, status=400)

        org = request.user.organization
        records = ActivityRecord.objects.for_org(org).filter(
            id__in=record_ids,
            state__in=["ingested", "needs_review", "approved"],
        )

        approved_ids = []
        errors = []
        for record in records:
            try:
                record._changed_by = request.user
                record.approve(request.user)
                approved_ids.append(str(record.id))
            except Exception as e:
                errors.append({"id": str(record.id), "error": str(e)})

        return Response({
            "approved": len(approved_ids),
            "approved_ids": approved_ids,
            "errors": errors,
        })


class LockRecordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        record = ActivityRecord.objects.for_org(request.user.organization).filter(pk=pk).first()
        if not record:
            return Response({"error": "Record not found."}, status=404)

        try:
            record.lock(request.user)
        except Exception as e:
            return Response({"error": str(e)}, status=400)

        return Response({"status": "locked", "locked_at": timezone.now().isoformat()})


# ---- Audit log (org-level) --------------------------------------------------

class OrgAuditLogView(generics.ListAPIView):
    serializer_class = RecordRevisionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        org = self.request.user.organization
        record_ids = ActivityRecord.objects.for_org(org).values_list("id", flat=True)
        return RecordRevision.objects.filter(
            activity_record_id__in=record_ids
        ).select_related("changed_by").order_by("-changed_at")
