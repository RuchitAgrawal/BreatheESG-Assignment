from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import (
    MeView,
    SourceFileListView,
    SourceFileDetailView,
    IngestSAPView,
    IngestUtilityView,
    IngestTravelView,
    ActivityRecordListView,
    ActivityRecordDetailView,
    ActivityRecordLineageView,
    ActivityRecordRevisionsView,
    ActivityRecordCalculationsView,
    BulkApproveView,
    LockRecordView,
    OrgAuditLogView,
)

urlpatterns = [
    # Auth
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="me"),

    # Source files
    path("source-files/", SourceFileListView.as_view(), name="source_file_list"),
    path("source-files/<uuid:pk>/", SourceFileDetailView.as_view(), name="source_file_detail"),

    # Ingestion
    path("ingest/sap/", IngestSAPView.as_view(), name="ingest_sap"),
    path("ingest/utility/", IngestUtilityView.as_view(), name="ingest_utility"),
    path("ingest/travel/", IngestTravelView.as_view(), name="ingest_travel"),

    # Records
    path("records/", ActivityRecordListView.as_view(), name="record_list"),
    path("records/bulk-approve/", BulkApproveView.as_view(), name="bulk_approve"),
    path("records/<uuid:pk>/", ActivityRecordDetailView.as_view(), name="record_detail"),
    path("records/<uuid:pk>/lineage/", ActivityRecordLineageView.as_view(), name="record_lineage"),
    path("records/<uuid:pk>/revisions/", ActivityRecordRevisionsView.as_view(), name="record_revisions"),
    path("records/<uuid:pk>/calculation/", ActivityRecordCalculationsView.as_view(), name="record_calculations"),
    path("records/<uuid:pk>/lock/", LockRecordView.as_view(), name="record_lock"),

    # Audit log
    path("audit-log/", OrgAuditLogView.as_view(), name="audit_log"),
]
