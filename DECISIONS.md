# Architectural Decision Records

Nine decisions that shaped the implementation. Each record covers the context, the alternatives considered, the decision, and what would change in production.

---

## ADR-001: SAP Integration via SE16N Flat File Export

**Status:** Accepted

**Context**

SAP has four common integration surfaces for external data pulls:

- **IDoc**: requires vendor pre-registration in transaction WE20, EDI partner profiles, and a middleware layer (XI/PI or Integration Suite). Setup time per client: 2-4 weeks minimum.
- **OData (SAP Gateway)**: requires SAP Gateway activation, OAuth setup, and client IT involvement to provision a service user. Not available in all ECC versions.
- **BAPI** (e.g. `BAPI_PO_GETITEMS`): requires RFC-capable network connectivity, pre-provisioned RFC credentials, and SAP authorisation profiles for the external user.
- **SE16N flat file**: analyst runs SE16N transaction, selects table (EKPO, MSEG, etc.), exports CSV. Zero integration overhead. Politically realistic for quarterly ESG bulk pulls at mid-market clients.

**Decision**

Use SE16N flat file CSV. The parser handles both English and German column headers (German locale is common in continental European SAP installs), SAP date formats (`YYYYMMDD` and `DD.MM.YYYY`), and movement type validation.

**Production path**

For clients with a dedicated SAP Basis team, OData is the cleaner option: it supports incremental pulls, eliminates the manual export step, and reduces lag from weeks to minutes. Migrate to OData when client has a provisioned Gateway and IT bandwidth.

---

## ADR-002: Utility Data via Portal CSV Export

**Status:** Accepted

**Context**

Options for utility data:

- **PDF bill parsing**: requires OCR, provider-specific layout training per utility company, fragile against layout changes.
- **GreenButton API**: standardised API for energy data, but requires OAuth and a utility provider partnership or client-side setup. Adoption varies significantly by region (common in the US, rare in the UK).
- **EDI 810/867**: standard for large industrial accounts, requires middleware.
- **Portal CSV export**: facilities manager logs in to utility portal, selects date range, exports. This is what teams actually do in practice.

**Decision**

Portal CSV. The parser uses flexible column aliasing (`billing_period_start` or `start_date`, `quantity` or `Quantity` or `consumption`) to handle format variations across providers.

**Known limitations**

- Reactive power rows (kVAR) and demand charge rows (kW) can appear in the same export. The parser does not currently filter these -- they would produce an incorrect kWh record. Production path: filter on a `record_type` or `tariff_description` column.
- Quarterly billing periods are not split automatically. The cross-month split warning is logged but the record is stored against the start date only.

**Production path**

GreenButton Connect My Data (CMD) for US clients, particularly utilities that support it (PG&E, SCE, ConEd). For UK clients, half-hourly settlement data (HH data) from the meter operator (MOP) via CSV or API.

---

## ADR-003: Travel Data via JSON Paste (Not API Integration)

**Status:** Accepted

**Context**

Concur has a REST API. Navan (TripActions), Egencia, and Cytric also have APIs. All of them require:

- OAuth 2.0 client credentials provisioned by the client IT/travel team
- API scope approval (SAP Concur's scope review process takes 2-4 weeks for production access)
- Per-client configuration

For a prototype, the realistic path is: analyst exports a travel expense report from Concur (File > Export > JSON or XML), copies the payload, and pastes it into our tool. Same data, zero integration overhead.

**Decision**

JSON paste via textarea. The parser handles the Concur-like trip/segment structure with flexible key aliasing (`departure_airport` or `from`, `arrival_airport` or `to`, etc.).

**Production path**

Concur SAP connector using the Expense Report v4 API and Trip v1 API. The JSON structure this parser handles is close enough to what the API returns that the parser requires minimal changes -- the main addition is pagination handling and incremental sync by `trip_modified_date`.

---

## ADR-004: Unit Normalization via Hardcoded Dict, Not pint

**Status:** Accepted

**Context**

The `pint` library is the standard Python unit conversion library. It handles 400+ unit types including temperature, pressure, and volume with full dimensional analysis.

Problems with pint for this use case:

- Fluid ounces vs weight ounces: pint cannot resolve this without context (density of the substance). A client reporting diesel in "oz" is ambiguous.
- Temperature units: Kelvin and Celsius differences matter for gas emission calculations but are rarely surfaced in ESG data.
- Setup and learning curve: pint's unit registry requires careful configuration. Getting it wrong silently produces incorrect results.
- The actual conversion requirement for this prototype is 5 pairs: `gal -> L`, `mi -> km`, `lb -> kg`, `kWh <-> MWh`, `short_ton -> metric_ton`.

**Decision**

Hardcoded dict of 5 conversion factors in `apps/records/units.py`. If a unit is not in the dict, the record is stored as-is with a `UNIT_NOT_NORMALIZED` quality note (yellow severity). This makes gaps visible rather than hiding them.

**Production path**

Per-client unit master table. Some clients report in short tons, others in metric tons, others in kg. The master table maps `(client_id, source_type, raw_unit) -> canonical_unit` with an explicit conversion factor. This also handles the fluid vs weight ounce ambiguity by requiring the client to configure it once.

---

## ADR-005: Scope Assignment as Code Constant, Not Database Table

**Status:** Accepted

**Context**

GHG Protocol scope assignments (1, 2, 3) are mostly deterministic by category: diesel combustion is always Scope 1, purchased electricity is always Scope 2, business travel is always Scope 3. However, there are legitimate exceptions:

- A client with a Power Purchase Agreement (PPA) covering 100% of consumption may report purchased electricity as Scope 1.
- A client with an on-site CHP plant may have Scope 1 electricity.
- Some carbon accounting frameworks treat certain Scope 3 categories differently.

**Decision**

Code constant (`SCOPE_RULES` dict in `apps/records/scopes.py`) for the prototype. The common cases are covered correctly. The uncommon cases are documented as a known limitation.

**Production path**

Database table `ScopeRule(organization, category, scope, valid_from, valid_to)` with per-org overrides. The lookup function falls back to the default rule if no org-specific override exists.

---

## ADR-006: EmissionCalculation is Append-Only

**Status:** Accepted

**Context**

Two approaches to storing emission calculations when an activity record is corrected:

1. **Update in place**: overwrite `co2e_kg` when the analyst corrects `quantity`. Simpler. No history.
2. **Append-only**: set `is_current = False` on the old row, insert a new row. Full recalculation history. Auditors can see what the CO2e was before and after the correction.

The assignment specification requires a "full audit trail". An auditor reviewing a locked record needs to see the exact calculation at the time of locking, not a post-hoc correction.

**Decision**

Append-only. `EmissionCalculation.save()` raises `ValidationError` on any attempt to change `co2e_kg`, `emission_factor`, or `activity_record` on an existing row. The only allowed update is `is_current = False`.

**Consequence**

The lineage drawer shows all historical calculations ordered by `calculated_at DESC`. The current calculation is highlighted. Superseded ones are shown at reduced opacity with a "Superseded" label.

---

## ADR-007: SHA-256 File Hash for Idempotent Ingestion

**Status:** Accepted

**Context**

Without deduplication, uploading the same CSV twice doubles the activity records. For ESG reporting this is a correctness issue: a company that accidentally re-ingests a quarterly SAP export will show double the Scope 1 emissions.

**Decision**

SHA-256 hash of the file contents (or JSON payload for travel). The hash is checked per-org before creating any records. If `(organization, file_hash)` already exists in `SourceFile`, the ingestion endpoint returns HTTP 200 with `already_ingested: true` and the existing `source_file_id`. No records are created.

**Limitation**

Content-hash deduplication only catches exact re-uploads. If the analyst modifies the CSV (adds or removes rows) and re-uploads, the hash differs and records are created. The production path is row-level deduplication by `(organization, EBELN, EBELP)` for SAP or `(organization, meter_id, billing_period_start)` for utility.

---

## ADR-008: Multi-Tenancy via ORM-Level Filtering, Not Row-Level Security

**Status:** Accepted

**Context**

Two approaches to data isolation in a multi-tenant system:

1. **PostgreSQL Row-Level Security (RLS)**: isolation enforced at the database level via `SET app.current_tenant` and a policy on each table. Impossible to leak cross-org data even if application code has a bug.
2. **ORM-level filtering**: every queryset goes through `TenantQuerySet.for_org(org)`. Requires discipline but no database-level config.

**Decision**

ORM-level filtering via `TenantQuerySet` and `TenantManager`. The `for_org(org)` method is the only entry point for all application queries. Views call it explicitly. It is tested by the seed command which verifies that Acme records are not visible to Globex.

Crucially, because this filtering happens at the base queryset level, any attempt by an authenticated user from Tenant A to access a record belonging to Tenant B (e.g. via direct ID access `GET /api/v1/records/<tenant-b-id>/`) will return a `404 Not Found` rather than a `403 Forbidden`. This is a strong security property that prevents cross-tenant ID enumeration attacks.

**Rationale**

RLS requires PostgreSQL-specific configuration and changes the `settings.py` connection setup (database-level session variables). For a prototype on Railway with SQLite in dev, RLS is impractical. The ORM approach is auditable from the code: you can grep for `for_org` to find every data access point.

**Production path**

Add RLS as an additional layer once the system is on PostgreSQL in production. Keep the `for_org()` filter in place as a redundant check.

---

## ADR-009: Short vs Long Haul Boundary from DEFRA 2023

**Status:** Accepted

**Context**

The DEFRA 2023 Greenhouse Gas Reporting Conversion Factors document defines two flight distance categories: short-haul and long-haul. The boundary is used to select the correct per-km emission factor.

Three approaches to the boundary:

1. **DEFRA 2023 Table 10**: 3,700 km. This is what DEFRA uses as the short/long-haul split in their published factors.
2. **ICAO definition**: varies by airline and route. Not a fixed number.
3. **Geography-based**: UK domestic vs international. Simpler but less precise.

**Decision**

Use the DEFRA 2023 Table 10 boundary of 3,700 km. This aligns with the factor table we use. A flight from LHR to DXB (5,484 km by Haversine) is long-haul. A flight from LHR to CDG (344 km) is short-haul.

**Class multiplier**

DEFRA 2023 publishes separate factors for economy, business, and first class. For this prototype, economy factors are applied to all classes. When a non-economy class is detected in the travel data, a `CLASS_FACTOR_NOT_APPLIED` quality note (yellow) is added. The analyst can see this in the lineage drawer and decide how to handle it.

The business class long-haul factor is approximately 2.9x the economy factor (DEFRA 2023 Table 10). Not applying this is a significant understatement for business travel. It is documented explicitly as a known limitation.
