import uuid
from django.db import models
from django.core.exceptions import ValidationError
from apps.core.models import Organization, User, TenantManager, TenantQuerySet
from apps.ingestion.models import SourceRow


# ---- ActivityRecord ----------------------------------------------------------

class ActivityRecordQuerySet(TenantQuerySet):
    """Extends TenantQuerySet to block bulk updates on locked records."""

    def update(self, **kwargs):
        # Prevent bulk update from bypassing the locked-state check in save()
        if "state" not in kwargs and self.filter(state="locked").exists():
            raise ValidationError(
                "Bulk update attempted on a queryset containing locked records. "
                "Filter locked records out before calling update()."
            )
        return super().update(**kwargs)

    def approved(self):
        return self.filter(state="approved")

    def needs_review(self):
        return self.filter(state="needs_review")

    def locked(self):
        return self.filter(state="locked")


class ActivityRecordManager(TenantManager):
    def get_queryset(self):
        return ActivityRecordQuerySet(self.model, using=self._db)


class ActivityRecord(models.Model):
    CATEGORY_CHOICES = [
        ("fuel_diesel", "Fuel - Diesel"),
        ("fuel_petrol", "Fuel - Petrol"),
        ("fuel_lpg", "Fuel - LPG"),
        ("electricity_grid", "Electricity (Grid)"),
        ("flight_short_haul", "Flight - Short Haul"),
        ("flight_long_haul", "Flight - Long Haul"),
        ("hotel_stay", "Hotel Stay"),
        ("ground_transport_car", "Ground Transport - Car"),
        ("ground_transport_rail", "Ground Transport - Rail"),
    ]
    SCOPE_CHOICES = [("1", "Scope 1"), ("2", "Scope 2"), ("3", "Scope 3")]
    STATE_CHOICES = [
        ("ingested", "Ingested"),
        ("needs_review", "Needs Review"),
        ("approved", "Approved"),
        ("locked", "Locked"),
    ]
    QUALITY_CHOICES = [
        ("green", "Green"),
        ("yellow", "Yellow"),
        ("red", "Red"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="activity_records"
    )
    # Nullable: manual entries have no source row
    source_row = models.OneToOneField(
        SourceRow, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="activity_record"
    )
    activity_date = models.DateField()
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    subcategory = models.CharField(max_length=255, blank=True)
    # Analyst can correct quantity -- this is intentionally mutable
    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    unit = models.CharField(max_length=30)           # original reported unit
    normalized_quantity = models.DecimalField(max_digits=15, decimal_places=4)
    normalized_unit = models.CharField(max_length=30)  # canonical: L, kWh, km, night
    scope = models.CharField(max_length=1, choices=SCOPE_CHOICES)
    state = models.CharField(max_length=15, choices=STATE_CHOICES, default="ingested")
    quality_tier = models.CharField(max_length=10, choices=QUALITY_CHOICES, default="green")
    # Array of {code, message, severity} dicts
    quality_notes = models.JSONField(default=list)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_records"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="locked_records"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ActivityRecordManager()

    class Meta:
        db_table = "activity_record"
        ordering = ["-activity_date", "-created_at"]

    def __str__(self):
        return f"{self.category} | {self.activity_date} | {self.organization.slug}"

    def save(self, *args, **kwargs):
        # Layer 1 of locked enforcement: block single-record saves on locked records.
        # Layer 2 (bulk queryset.update) is handled in ActivityRecordQuerySet.update().
        if self.pk:
            try:
                original = ActivityRecord.objects.get(pk=self.pk)
                if original.state == "locked":
                    raise ValidationError(
                        f"ActivityRecord {self.pk} is locked for audit and cannot be modified. "
                        "Create a new record or contact an administrator."
                    )
            except ActivityRecord.DoesNotExist:
                pass  # new record, no conflict
        super().save(*args, **kwargs)

    # ---- State transition helpers --------------------------------------------

    def approve(self, user):
        if self.state == "locked":
            raise ValidationError("Cannot approve a locked record.")
        if self.state not in ("ingested", "needs_review", "approved"):
            raise ValidationError(f"Cannot approve from state '{self.state}'.")
        from django.utils import timezone
        self.state = "approved"
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.save()

    def lock(self, user):
        if self.state != "approved":
            raise ValidationError(
                f"Cannot lock a record in state '{self.state}'. Must be 'approved' first."
            )
        from django.utils import timezone
        self.state = "locked"
        self.locked_by = user
        self.locked_at = timezone.now()
        # Skip the locked check in save() -- this is the intentional lock action
        # We call super().save() directly to avoid circular check
        ActivityRecord.objects.filter(pk=self.pk).update(
            state="locked",
            locked_by=user,
            locked_at=timezone.now(),
        )


# ---- RecordRevision (append-only audit log) ---------------------------------

class RecordRevision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity_record = models.ForeignKey(
        ActivityRecord, on_delete=models.CASCADE, related_name="revisions"
    )
    changed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="revisions_made"
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(null=True, blank=True)
    new_value = models.TextField(null=True, blank=True)
    change_reason = models.TextField(blank=True)

    class Meta:
        db_table = "record_revision"
        ordering = ["-changed_at"]

    def save(self, *args, **kwargs):
        # Append-only: no updates allowed on existing revisions
        if self.pk and RecordRevision.objects.filter(pk=self.pk).exists():
            raise ValidationError("RecordRevision is append-only and cannot be updated.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.field_name}: {self.old_value} -> {self.new_value} ({self.changed_at})"
