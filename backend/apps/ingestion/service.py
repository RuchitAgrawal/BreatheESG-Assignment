"""
Ingestion service: orchestrates parser -> SourceRow -> ActivityRecord -> EmissionCalculation.

This is the core pipeline. Each source type calls its parser, persists raw rows,
normalizes into ActivityRecords, and auto-creates EmissionCalculations.

EmissionCalculation creation flow (documented in MODEL.md):
1. Parse raw row -> SourceRow (raw_payload preserved)
2. Normalize -> ActivityRecord (state = ingested or needs_review)
3. Look up matching EmissionFactor by category + date range
4. INSERT EmissionCalculation (calculated_by = null = system)

If no matching EmissionFactor exists, the record gets quality_note NO_FACTOR
and state = needs_review. No EmissionCalculation is created until resolved.
"""

import hashlib
import json
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.models import Organization, User
from apps.ingestion.models import SourceFile, SourceRow
from apps.records.models import ActivityRecord
from apps.records.scopes import get_scope
from apps.records.units import normalize_quantity, assign_quality_tier, assign_state_from_quality
from apps.emissions.models import EmissionFactor, EmissionCalculation


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _result_to_payload(result, parser_name: str) -> dict:
    """Convert a ParseResult to a JSON-serializable dict for raw_payload storage."""
    d = {"_parser": parser_name, "status": result.status, "error": result.error}
    if hasattr(result, "activity_date") and result.activity_date:
        d["activity_date"] = str(result.activity_date)
    if hasattr(result, "category"):
        d["category"] = result.category
    if hasattr(result, "quantity") and result.quantity is not None:
        d["quantity"] = str(result.quantity)
    if hasattr(result, "unit"):
        d["unit"] = result.unit
    if hasattr(result, "subcategory"):
        d["subcategory"] = result.subcategory
    if hasattr(result, "quality_notes"):
        d["quality_notes"] = result.quality_notes
    # Travel-specific fields
    for field in ("trip_id", "traveler_email", "segment_index", "billing_period_start", "billing_period_end"):
        val = getattr(result, field, None)
        if val is not None:
            d[field] = str(val)
    return d



def find_emission_factor(category: str, activity_date: date) -> EmissionFactor | None:
    from django.db.models import Q
    return (
        EmissionFactor.objects
        .filter(category=category, valid_from__lte=activity_date)
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=activity_date))
        .order_by("-valid_from")
        .first()
    )


def create_emission_calculation(record: ActivityRecord, user=None) -> EmissionCalculation | None:
    """
    Create an EmissionCalculation for an ActivityRecord.
    Returns None if no matching factor is found.
    """
    factor = find_emission_factor(record.category, record.activity_date)
    if factor is None:
        return None

    co2e = record.normalized_quantity * factor.factor_value
    notes_text = (
        f"{record.normalized_quantity} {record.normalized_unit} "
        f"* {factor.factor_value} kgCO2e/{factor.unit} "
        f"= {co2e:.4f} kgCO2e "
        f"[{factor.source}, {factor.name}]"
    )

    return EmissionCalculation.objects.create(
        activity_record=record,
        emission_factor=factor,
        co2e_kg=co2e.quantize(Decimal("0.0001")),
        calculation_notes=notes_text,
        calculated_by=user,
        is_current=True,
    )


def _build_activity_record_from_result(
    result, org: Organization, source_row: SourceRow
) -> ActivityRecord:
    """Convert a ParseResult into an ActivityRecord (not saved yet)."""
    notes = list(result.quality_notes)

    norm_qty, norm_unit = normalize_quantity(result.quantity, result.unit, result.category)

    # Flag if unit conversion was not possible (unit stayed unchanged but differs from canonical)
    from apps.records.units import CANONICAL_UNITS
    canonical = CANONICAL_UNITS.get(result.category, result.unit)
    if norm_unit != canonical:
        notes.append({
            "code": "UNIT_NOT_NORMALIZED",
            "severity": "yellow",
            "message": (
                f"Unit '{result.unit}' could not be converted to canonical unit '{canonical}'. "
                "Stored as-is. Emission calculation may be incorrect."
            ),
        })

    quality_tier = assign_quality_tier(notes)
    state = assign_state_from_quality(quality_tier)

    return ActivityRecord(
        organization=org,
        source_row=source_row,
        activity_date=result.activity_date,
        category=result.category,
        subcategory=result.subcategory,
        quantity=result.quantity,
        unit=result.unit,
        normalized_quantity=norm_qty,
        normalized_unit=norm_unit,
        scope=get_scope(result.category),
        state=state,
        quality_tier=quality_tier,
        quality_notes=notes,
    )


@transaction.atomic
def ingest_sap(content: bytes, filename: str, org: Organization, user: User) -> dict:
    from apps.ingestion.sap_parser import parse_sap_csv

    file_hash = _sha256(content)

    # Org-scoped idempotency check
    existing = SourceFile.objects.filter(organization=org, file_hash=file_hash).first()
    if existing:
        return {
            "already_ingested": True,
            "source_file_id": str(existing.id),
            "message": f"File already ingested on {existing.created_at.date()}.",
        }

    source_file = SourceFile.objects.create(
        organization=org,
        uploaded_by=user,
        source_type="sap",
        filename=filename,
        file_hash=file_hash,
        storage_path=f"media/uploads/sap/{file_hash[:16]}_{filename}",
        status="processing",
    )

    results = parse_sap_csv(content)
    row_count = 0
    error_count = 0

    for i, result in enumerate(results, start=1):
        source_row = SourceRow.objects.create(
            source_file=source_file,
            row_index=i,
            raw_payload=_result_to_payload(result, "sap"),
            parse_status="ok" if result.status == "ok" else "failed",
            parse_error=result.error if result.status != "ok" else None,
        )

        if result.status != "ok" or result.activity_date is None:
            error_count += 1
            continue

        row_count += 1
        record = _build_activity_record_from_result(result, org, source_row)
        record.save()

        calc = create_emission_calculation(record)
        if calc is None:
            record.quality_notes = record.quality_notes + [{
                "code": "NO_FACTOR",
                "severity": "red",
                "message": (
                    f"No emission factor found for category '{record.category}' "
                    f"on date {record.activity_date}. "
                    "Seeding emission_factors fixture is required."
                ),
            }]
            record.quality_tier = "red"
            record.state = "needs_review"
            record.save()

    source_file.status = "completed"
    source_file.row_count = row_count
    source_file.error_count = error_count
    source_file.save()

    return {
        "already_ingested": False,
        "source_file_id": str(source_file.id),
        "row_count": row_count,
        "error_count": error_count,
        "status": "completed",
    }


@transaction.atomic
def ingest_utility(content: bytes, filename: str, org: Organization, user: User) -> dict:
    from apps.ingestion.utility_parser import parse_utility_csv

    file_hash = _sha256(content)
    existing = SourceFile.objects.filter(organization=org, file_hash=file_hash).first()
    if existing:
        return {
            "already_ingested": True,
            "source_file_id": str(existing.id),
            "message": f"File already ingested on {existing.created_at.date()}.",
        }

    source_file = SourceFile.objects.create(
        organization=org,
        uploaded_by=user,
        source_type="utility",
        filename=filename,
        file_hash=file_hash,
        storage_path=f"media/uploads/utility/{file_hash[:16]}_{filename}",
        status="processing",
    )

    results = parse_utility_csv(content)
    row_count = 0
    error_count = 0

    for i, result in enumerate(results, start=1):
        source_row = SourceRow.objects.create(
            source_file=source_file,
            row_index=i,
            raw_payload=_result_to_payload(result, "utility"),
            parse_status="ok" if result.status == "ok" else "failed",
            parse_error=result.error if result.status != "ok" else None,
        )

        if result.status != "ok" or result.activity_date is None:
            error_count += 1
            continue

        row_count += 1
        record = _build_activity_record_from_result(result, org, source_row)
        record.save()

        calc = create_emission_calculation(record)
        if calc is None:
            record.quality_notes = record.quality_notes + [{
                "code": "NO_FACTOR", "severity": "red",
                "message": f"No emission factor for '{record.category}' on {record.activity_date}.",
            }]
            record.quality_tier = "red"
            record.state = "needs_review"
            record.save()

    source_file.status = "completed"
    source_file.row_count = row_count
    source_file.error_count = error_count
    source_file.save()

    return {
        "already_ingested": False,
        "source_file_id": str(source_file.id),
        "row_count": row_count,
        "error_count": error_count,
        "status": "completed",
    }


@transaction.atomic
def ingest_travel(payload: dict, report_name: str, org: Organization, user: User) -> dict:
    from apps.ingestion.travel_parser import parse_travel_json

    content_bytes = json.dumps(payload, sort_keys=True).encode()
    file_hash = _sha256(content_bytes)

    existing = SourceFile.objects.filter(organization=org, file_hash=file_hash).first()
    if existing:
        return {
            "already_ingested": True,
            "source_file_id": str(existing.id),
            "message": f"Report already ingested on {existing.created_at.date()}.",
        }

    source_file = SourceFile.objects.create(
        organization=org,
        uploaded_by=user,
        source_type="travel",
        filename=report_name,
        file_hash=file_hash,
        storage_path=f"media/uploads/travel/{file_hash[:16]}_{report_name}.json",
        status="processing",
    )

    results = parse_travel_json(payload)
    row_count = 0
    error_count = 0

    for i, result in enumerate(results, start=1):
        source_row = SourceRow.objects.create(
            source_file=source_file,
            row_index=i,
            raw_payload=_result_to_payload(result, "travel"),
            parse_status="ok" if result.status == "ok" else "failed",
            parse_error=result.error if result.status != "ok" else None,
        )

        if result.status != "ok" or result.activity_date is None or result.quantity is None:
            error_count += 1
            continue

        row_count += 1
        record = _build_activity_record_from_result(result, org, source_row)
        record.save()

        calc = create_emission_calculation(record)
        if calc is None:
            record.quality_notes = record.quality_notes + [{
                "code": "NO_FACTOR", "severity": "red",
                "message": f"No emission factor for '{record.category}' on {record.activity_date}.",
            }]
            record.quality_tier = "red"
            record.state = "needs_review"
            record.save()

    source_file.status = "completed"
    source_file.row_count = row_count
    source_file.error_count = error_count
    source_file.save()

    return {
        "already_ingested": False,
        "source_file_id": str(source_file.id),
        "row_count": row_count,
        "error_count": error_count,
        "status": "completed",
    }
