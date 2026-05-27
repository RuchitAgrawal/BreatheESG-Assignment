import uuid
from django.db import models
from apps.core.models import Organization, User, TenantManager


class SourceFile(models.Model):
    SOURCE_TYPE_CHOICES = [
        ("sap", "SAP Procurement"),
        ("utility", "Utility CSV"),
        ("travel", "Corporate Travel"),
    ]
    STATUS_CHOICES = [
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="source_files"
    )
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="uploaded_files"
    )
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES)
    filename = models.CharField(max_length=500)
    file_hash = models.CharField(max_length=64)  # SHA-256 hex
    storage_path = models.CharField(max_length=1000)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="processing")
    row_count = models.IntegerField(null=True, blank=True)
    error_count = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()

    class Meta:
        db_table = "source_file"
        # Org-scoped idempotency: same file cannot be uploaded twice to same org
        unique_together = [("organization", "file_hash")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.source_type} / {self.filename} ({self.organization.slug})"


class SourceRow(models.Model):
    PARSE_STATUS_CHOICES = [
        ("ok", "OK"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_file = models.ForeignKey(
        SourceFile, on_delete=models.CASCADE, related_name="rows"
    )
    # 1-indexed position in the original file -- used in the lineage view
    row_index = models.IntegerField()
    # Exact original row before normalization. Enables replay if normalization logic changes.
    raw_payload = models.JSONField()
    parse_status = models.CharField(
        max_length=10, choices=PARSE_STATUS_CHOICES, default="ok"
    )
    # Null when parse_status = ok
    parse_error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "source_row"
        unique_together = [("source_file", "row_index")]
        ordering = ["source_file", "row_index"]

    def __str__(self):
        return f"Row {self.row_index} of {self.source_file.filename}"
