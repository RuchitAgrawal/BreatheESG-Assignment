# Tradeoffs

Three deliberate gaps in this prototype. Each one describes what was chosen, what was sacrificed, and what the production path looks like.

---

## Tradeoff 1: No Bulk Edit UI

**What was chosen**

Individual record editing via the "Correct quantity" form in the lineage drawer. One record at a time, one field at a time (quantity and subcategory).

**What was given up**

An analyst working with a 200-row SAP export where the plant code is wrong on every row cannot fix all 200 records through the UI -- they would need to manually open and edit each one. In practice, the realistic response to a systematic source error is to reject the entire batch, have the client fix the source file, and re-upload. Re-upload is idempotent by SHA-256 hash (the new file produces a new hash, so the corrected records are created alongside the originals).

The UX gap is real: there is no way to bulk-correct a field value across a set of filtered records. A production bulk edit feature requires:
- Multi-select preview (show what will change before committing)
- Per-row validation (some records may be locked, some in incompatible states)
- Undo/redo or at minimum a confirmation modal with row count
- Conflict resolution for concurrent editors (two analysts editing the same batch)

This is 2-4 days of careful frontend work with corresponding backend batch-update endpoint hardening.

**Production path**

Django admin bulk action framework as a starting point: select rows, choose action "Correct unit for selected records", enter new value, confirm. The admin framework handles multi-select and provides a confirmation step for free. For the analyst-facing UI, a dedicated bulk edit drawer with a preview diff before commit.

---

## Tradeoff 2: Locked Records Never Recalculate on Factor Update

**What was chosen**

When a record is locked for audit, its `EmissionCalculation` is pinned to the exact `EmissionFactor` version used at calculation time (via FK). If DEFRA releases 2024 factors next year, locked records keep their 2023 calculation. A new `EmissionFactor` row is inserted with `valid_from = 2024-01-01`, and only new ingestions after that date pick up the 2024 factor.

**What was given up**

If a client discovers that a factor was incorrect (not a new factor, but an error in the factor used), correcting it requires manually unlocking records, deleting or superseding the old calculation, and re-approving. There is no admin workflow for "re-run calculations for all records in org using updated factors."

This is intentionally conservative. Silently recalculating locked records when a factor changes would be an audit integrity failure -- an auditor reviewing the signed-off figures would see different numbers than what the analyst approved.

**What this means in practice**

A UK electricity consumer who locked their records using the 2022 factor (0.233 kgCO2e/kWh) would show different figures than one who locked using 2023 (0.207 kgCO2e/kWh). Both are correct for their respective reporting periods. The DEFRA guidance explicitly states that historical records should use the factors current at the time of reporting.

**Production path**

A factor update workflow with explicit analyst-triggered recalculation per batch and supervisor sign-off. The flow:
1. Admin marks old `EmissionFactor` as `valid_to = yesterday`.
2. Inserts new factor with `valid_from = today`.
3. System identifies affected records: `EmissionCalculation` where `emission_factor_id = old_factor AND activity_record.state != locked`.
4. Analyst reviews affected records, triggers recalculation with confirmation.
5. Each recalculation: sets old `EmissionCalculation.is_current = False`, inserts new one, writes a `RecordRevision` row with `change_reason = "Factor update: DEFRA 2023 -> DEFRA 2024"`.

Locked records are explicitly excluded from step 3. Any locked record that needs recalculation requires an admin-level unlock action with audit justification.

---

## Tradeoff 3: Single Global Emission Factor per Category (No Regional Variation)

**What was chosen**

One emission factor per category, from DEFRA 2023 UK factors. All clients use the same factor regardless of geography.

**What was given up**

UK grid intensity in 2023: 0.207 kgCO2e/kWh.
US average grid intensity in 2023: approximately 0.386 kgCO2e/kWh (EPA eGRID).
France: approximately 0.052 kgCO2e/kWh (nuclear-heavy grid, Agence de l'Environnement).
Norway: approximately 0.016 kgCO2e/kWh (almost entirely hydro).

A client with data centers in France and manufacturing facilities in the US, using the UK factor for both, will produce materially wrong Scope 2 figures. France would be overstated by 4x. The US would be understated by nearly 2x.

This also applies to road transport: the UK average car emission factor is 0.170 kgCO2e/km. A US client using a mix of large pickup trucks would have a significantly higher per-km figure. The European fleet average is lower than the UK figure.

**Why this is acceptable for the prototype**

The prototype data is deliberately UK-centric (DEFRA factors, UK utility CSV format, GBP-denominated travel). Multi-region factor handling requires a client profile (which country is each meter or plant located in?) that is not present in this data model. Applying an incorrect regional factor silently is worse than the current behavior, where the factor source is visible in the lineage drawer and the SOURCES.md documents the limitation explicitly.

GHG Protocol distinguishes location-based and market-based Scope 2 accounting. Market-based accounts for renewable energy certificates and PPAs, which can reduce Scope 2 to near-zero even if the local grid is carbon-intensive. This distinction is also not implemented -- another known limitation.

**Production path**

Add a `region` column to `EmissionFactor`. Add a `country_code` or `region` field to `Organization` (and optionally to individual `ActivityRecord` rows for assets in multiple countries). Update `find_emission_factor()` to prefer a region-specific factor and fall back to global. Source factors from:
- UK: DEFRA annual conversion factors
- US: EPA eGRID by utility balancing authority (sub-regional, more precise than national average)
- EU: EEA country-level grid factors
- Other: IEA regional electricity emissions data

For market-based Scope 2: add a `RenewableEnergyCertificate` model linked to a meter and date range, with a residual mix factor applied when the certificate covers the billing period.
