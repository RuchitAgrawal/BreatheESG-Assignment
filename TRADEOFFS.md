# Tradeoffs

Three deliberate tradeoffs made in this prototype. Each one describes what was chosen, what was given up, and what the production path looks like.

---

## Tradeoff 1: SQLite in Development vs PostgreSQL in Production

**What was chosen**

SQLite for local development. No Docker Compose, no local Postgres, no setup friction. Run `python manage.py migrate` and it works.

**What was given up**

- `JSONField` on SQLite does not support GIN indexes. Querying `quality_notes` by code or severity requires a full scan in dev.
- `DecimalField` precision semantics differ slightly between SQLite and PostgreSQL. The `EmissionCalculation.co2e_kg` field uses `Decimal("0.0001")` quantization in Python, which makes the results consistent regardless of backend, but this adds a Python-level rounding step that would not be needed on PostgreSQL.
- PostgreSQL-specific features (RLS, `GENERATED ALWAYS`, `pg_trgm` for fuzzy search) cannot be tested locally without an additional setup step.

**Production path**

`dj-database-url` is already wired into `settings.py`. Set `DATABASE_URL` and the switch is automatic. The `ATOMIC_REQUESTS = True` setting and all ORM usage is backend-agnostic. No application code changes are required.

**Why this tradeoff was acceptable**

The data volume for a prototype is small. The slowest query (audit log with 75+ revision rows across 3 orgs) runs in under 5ms on SQLite. The correctness-critical behavior (immutability enforcement, locked record checks, SHA-256 dedup) is all in Python, not in SQL, so the backend difference does not affect it.

---

## Tradeoff 2: Economy-Class Factors for All Business Flights

**What was chosen**

DEFRA 2023 economy class per-km factors applied to all flight segments regardless of cabin class. When a non-economy class is detected, a `CLASS_FACTOR_NOT_APPLIED` yellow quality note is added and the record moves to `needs_review`.

**What was given up**

Accuracy for business and first class travel. DEFRA 2023 Table 10 publishes the following per-passenger-km factors for long-haul flights:

| Class | Factor (kgCO2e/km) |
|-------|-------------------|
| Economy | 0.195 |
| Premium economy | 0.287 |
| Business | 0.429 |
| First | 0.599 |

Business class long-haul is 2.2x economy. First class is 3.1x. For a company where executives fly business class on long-haul routes, the understatement is significant.

**Why this tradeoff was acceptable for a prototype**

The class multiplier requires the travel expense system to report cabin class reliably. In practice, Concur records cabin class inconsistently: it may show "Business" for a fare class code that is actually premium economy, or leave it blank entirely. Applying an incorrect multiplier confidently is worse than flagging it for review. The quality note makes the gap visible and actionable.

**Production path**

- Store cabin class on the `ActivityRecord` subcategory field (already done for the travel parser).
- Add a `cabin_class` field to `EmissionFactor` and create separate factor rows for each class.
- Update `find_emission_factor()` to prefer a class-specific factor and fall back to economy if not found.
- Add a migration to backfill existing flight records.

---

## Tradeoff 3: Haversine Great-Circle Distance vs Actual Flight Path

**What was chosen**

Haversine formula for calculating flight distance when the travel data does not include a pre-computed distance. Uses a fixed airport coordinate set of 20 major hubs.

**What was given up**

- **Accuracy**: Haversine uses a mean Earth radius of 6,371 km and treats the Earth as a sphere. The WGS84 ellipsoid model (used by GPS) gives results that differ by up to 0.5% for long-haul routes. For a LHR-JFK flight (5,541 km by Haversine), the error is about 28 km, which translates to about 5.5 kgCO2e at the economy class factor.
- **Route fidelity**: great-circle distance is the theoretical minimum distance between two points. Actual flight paths deviate due to jet streams, airspace restrictions, overflight fees, and preferred routings. A typical transatlantic flight is 3-8% longer than great-circle. DEFRA guidance acknowledges this and recommends applying a radiative forcing index (RFI) multiplier of 1.891 for long-haul flights to account for non-CO2 effects. This prototype does not apply RFI.
- **Airport coverage**: the 20-airport hardcoded set covers approximately 80% of corporate business travel by volume (major hubs in North America, Europe, Asia-Pacific, Middle East). Routes to secondary airports (e.g. BHX, ORF, TRV) fail with a `DISTANCE_MISSING` red note.

**Why this tradeoff was acceptable**

For the prototype, the distance calculation is a fallback for when the travel system did not provide a distance. If the source data includes `distance_km`, that value is used as-is and Haversine is not invoked. The error from Haversine is smaller than the error from applying economy factors to business class travel.

**Production path**

- Integrate the OurAirports dataset (7,000+ airports, CC0 license, updated monthly). Load into a `Airport(iata_code, lat, lon)` table and look up at parse time.
- Switch Haversine to `geopy.distance.geodesic` (Vincenty/Karney method) for sub-meter accuracy.
- Apply DEFRA's radiative forcing uplift (1.891x for long-haul) as a separate quality-tier-green step documented in `calculation_notes`.
