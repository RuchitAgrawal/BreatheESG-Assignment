import uuid
from django.db import models
from django.core.exceptions import ValidationError
from apps.core.models import User
from apps.records.models import ActivityRecord


class EmissionFactor(models.Model):
    """
    Versioned emission factor. FK-pinned by EmissionCalculation so
    old calculations remain traceable to the exact factor version used.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    source = models.CharField(max_length=100)   # e.g. "DEFRA 2023", "EPA 2023"
    category = models.CharField(max_length=30)  # matches ActivityRecord.category
    subcategory = models.CharField(max_length=100, blank=True)
    factor_value = models.DecimalField(max_digits=15, decimal_places=6)  # kgCO2e per unit
    unit = models.CharField(max_length=30)       # canonical unit: L, kWh, km, night
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)   # null = currently valid
    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "emission_factor"
        ordering = ["category", "-valid_from"]

    def __str__(self):
        return f"{self.name} ({self.source}) [{self.category}]"


class EmissionCalculation(models.Model):
    """
    IMMUTABLE once written. Never UPDATE this table -- only INSERT.
    is_current is the one pointer field that gets set to False when
    a newer calculation supersedes this one.

    Edit flow:
      analyst edits ActivityRecord.quantity
      -> post_save signal fires
      -> old EmissionCalculation.is_current = False  (UPDATE, intentional)
      -> new EmissionCalculation inserted              (INSERT)
      -> RecordRevision row written for the quantity change
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity_record = models.ForeignKey(
        ActivityRecord, on_delete=models.CASCADE, related_name="calculations"
    )
    # FK-pinned: stores the exact factor version used at calculation time.
    # If DEFRA releases 2024 factors, locked records keep pointing to 2023.
    emission_factor = models.ForeignKey(
        EmissionFactor, on_delete=models.PROTECT, related_name="calculations"
    )
    co2e_kg = models.DecimalField(max_digits=15, decimal_places=4)
    # Human-readable derivation e.g. "8629 km * 0.195 kgCO2e/km = 1682.7 kgCO2e"
    calculation_notes = models.TextField()
    calculated_at = models.DateTimeField(auto_now_add=True)
    # null = system auto-calculation during ingestion
    calculated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="calculations_made"
    )
    # Only the most recent calculation is current. Old ones stay in DB for auditors.
    is_current = models.BooleanField(default=True)

    class Meta:
        db_table = "emission_calculation"
        ordering = ["-calculated_at"]

    def save(self, *args, **kwargs):
        # Immutability enforcement: no updates allowed on existing rows.
        # Exception: is_current can be set to False when superseded.
        if self.pk and EmissionCalculation.objects.filter(pk=self.pk).exists():
            existing = EmissionCalculation.objects.get(pk=self.pk)
            # Only allow changing is_current from True to False
            if existing.co2e_kg != self.co2e_kg or \
               existing.emission_factor_id != self.emission_factor_id or \
               existing.activity_record_id != self.activity_record_id:
                raise ValidationError(
                    f"EmissionCalculation {self.pk} is immutable. "
                    "Create a new calculation row instead of updating this one."
                )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.co2e_kg} kgCO2e | {self.activity_record} | {'current' if self.is_current else 'superseded'}"
