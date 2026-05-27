# Model Reference

This document describes every persistent entity in the system, its invariants, and how they relate.

---

## Organization

Tenant root. Every other entity belongs to exactly one organization. Rows from different organizations are never mixed in any query -- `TenantQuerySet.for_org(org)` is called at the boundary of every view.

```
Organization
  id          UUID PK
  name        str
  slug        str  UNIQUE
  created_at  datetime
```

Slug is used as the org identifier in seed commands and deployment scripts. It is immutable after creation.

---

## User

Custom `AbstractBaseUser`. Email is the login identifier, not username. Role is a two-value enum: `analyst` or `admin`. The distinction is not enforced at the model layer yet -- it is available for view-level permission checks in production.

```
User
  id            UUID PK
  organization  FK -> Organization
  email         str UNIQUE
  role          enum(analyst, admin)
  first_name    str
  last_name     str
  is_active     bool
  created_at    datetime
```

`TenantManager.create_user()` requires `organization` at creation. There is no path to create a user without an org.

---

## SourceFile

One row per uploaded file or submitted payload. Stores enough metadata to reproduce the ingestion without re-uploading.

```
SourceFile
  id            UUID PK
  organization  FK -> Organization
  uploaded_by   FK -> User (nullable)
  source_type   enum(sap, utility, travel)
  filename      str
  file_hash     SHA-256 hex
  storage_path  str
  status        enum(processing, completed, failed)
  row_count     int (nullable until processing complete)
  error_count   int (nullable until processing complete)
  created_at    datetime
```

`(organization, file_hash)` has a unique check in the ingestion service (not a DB constraint, because the hash is computed in Python). Re-uploading the same file for the same org returns the existing `SourceFile.id` with `already_ingested: true`. No duplicate `SourceRow` records are created.

---

## SourceRow

One row per input data row. The `raw_payload` column is a JSONB snapshot of what the parser saw, after header normalization but before any transformation. This is the audit anchor: if the normalization logic changes, you can replay it from `raw_payload` without re-uploading the original file.

```
SourceRow
  id            UUID PK
  source_file   FK -> SourceFile
  row_index     int
  raw_payload   JSONB
  parse_status  enum(ok, failed)
  parse_error   str (nullable)
  created_at    datetime
```

`parse_error` is populated for rows the parser rejected (Period 13, reversal docs, missing required fields). These rows still get a `SourceRow` record so the failure is visible in the UI and queryable.

---

## ActivityRecord

The central entity. Represents one normalized activity event after parsing and unit conversion.

```
ActivityRecord
  id                  UUID PK
  organization        FK -> Organization
  source_row          FK -> SourceRow (nullable -- for future manual entry)
  activity_date       date
  category            str
  subcategory         str
  quantity            Decimal  -- original quantity as parsed
  unit                str      -- original unit as parsed
  normalized_quantity Decimal  -- after unit conversion
  normalized_unit     str      -- canonical unit for this category
  scope               enum(1, 2, 3)
  state               enum  -- see state machine below
  quality_tier        enum(green, yellow, red)
  quality_notes       JSONB[]  -- list of {code, severity, message}
  reviewed_by         FK -> User (nullable)
  reviewed_at         datetime (nullable)
  locked_by           FK -> User (nullable)
  locked_at           datetime (nullable)
  created_at          datetime
  updated_at          datetime
```

### State Machine

```
ingested ----[approve()]--> approved ----[lock()]--> locked
    |
    +--[quality_tier red/yellow]--> needs_review --[approve()]--> approved
```

State transitions are enforced by named methods on the model:

- `approve(user)` -- sets state to `approved`, records `reviewed_by` and `reviewed_at`
- `lock(user)` -- requires current state is `approved`, sets state to `locked`, records `locked_by` and `locked_at`

### Locked Enforcement

Two layers:

1. `ActivityRecord.save()` raises `ValidationError` if `state == locked` and any tracked field changed.
2. `ActivityRecordQuerySet.update()` raises `ValidationError` if any record in the queryset has `state == locked`.

This means both the ORM `.save()` path and the `.update()` path are covered. A bulk update that includes a locked record will fail entirely (no partial updates).

### Quality Tier

Derived from `quality_notes` at ingestion time by `assign_quality_tier()`:

- `red` if any note has `severity == red`
- `yellow` if any note has `severity == yellow` (and no red)
- `green` if all notes are green or there are no notes

A record with `quality_tier == red` or `yellow` gets `state == needs_review` automatically. The analyst must review and explicitly approve it.

---

## RecordRevision

Append-only audit log. One row per field change on an `ActivityRecord`. Written by a `pre_save` signal that snapshots tracked fields before save and a `post_save` signal that compares and writes revision rows.

```
RecordRevision
  id               UUID PK
  activity_record  FK -> ActivityRecord
  changed_by       FK -> User (nullable -- null means system)
  field_name       str
  old_value        str (nullable)
  new_value        str (nullable)
  change_reason    str
  changed_at       datetime auto
```

Tracked fields: `state`, `quantity`, `subcategory`, `quality_tier`.

This table is never updated or deleted. The only operation is INSERT.

---

## EmissionFactor

Versioned emission factor. Factor values are pinned by foreign key in `EmissionCalculation`, so changing or adding a new factor version does not retroactively alter existing calculations.

```
EmissionFactor
  id            UUID PK
  name          str
  source        str   -- e.g. "DEFRA 2023"
  category      str   -- matches ActivityRecord.category
  subcategory   str
  factor_value  Decimal(15, 6)  -- kgCO2e per unit
  unit          str              -- canonical unit
  valid_from    date
  valid_to      date (nullable -- null means currently active)
  version       int
  created_at    datetime
```

Factor lookup: `category == record.category AND valid_from <= record.activity_date AND (valid_to IS NULL OR valid_to >= record.activity_date)`. Multiple matching rows are ordered by `valid_from DESC` and the most recent is used.

---

## EmissionCalculation

Immutable once written. The `save()` method enforces this: any attempt to change `co2e_kg`, `emission_factor`, or `activity_record` on an existing row raises `ValidationError`.

The single allowed update is `is_current = False`, which happens when a recalculation supersedes this row. Old rows are kept permanently for audit.

```
EmissionCalculation
  id               UUID PK
  activity_record  FK -> ActivityRecord
  emission_factor  FK -> EmissionFactor  -- FK-pinned to exact version used
  co2e_kg          Decimal(15, 4)
  calculation_notes  str  -- human-readable derivation, e.g. "500 L * 2.5164 kgCO2e/L = 1258.2 kgCO2e [DEFRA 2023]"
  calculated_at    datetime auto
  calculated_by    FK -> User (nullable -- null = system auto-calculation)
  is_current       bool
```

### Recalculation Flow

When an analyst edits `ActivityRecord.quantity`:

1. Pre-save signal snapshots old quantity.
2. Post-save signal writes a `RecordRevision` row.
3. View calls `EmissionCalculation.objects.filter(activity_record=record, is_current=True).update(is_current=False)`.
4. View calls `create_emission_calculation(record, user=request.user)` to insert a new row.

Step 3 is the one intentional UPDATE on this table. It only touches `is_current`.

---

## Category Values

| Category | Scope | Canonical Unit | DEFRA Factor Source |
|----------|-------|---------------|---------------------|
| fuel_diesel | 1 | L | DEFRA 2023 Table 3 |
| fuel_petrol | 1 | L | DEFRA 2023 Table 3 |
| fuel_lpg | 1 | L | DEFRA 2023 Table 3 |
| electricity_grid | 2 | kWh | DEFRA 2023 Table 12 |
| flight_short_haul | 3 | km | DEFRA 2023 Table 10 (< 3,700 km) |
| flight_long_haul | 3 | km | DEFRA 2023 Table 10 (>= 3,700 km) |
| hotel_stay | 3 | night | DEFRA 2023 Table 16 |
| ground_transport_car | 3 | km | DEFRA 2023 Table 5 |
| ground_transport_rail | 3 | km | DEFRA 2023 Table 5 |

Scope assignment is a code constant in `apps/records/scopes.py`. The production path is a DB table with per-org overrides (some PPA structures reclassify purchased electricity as Scope 1).
