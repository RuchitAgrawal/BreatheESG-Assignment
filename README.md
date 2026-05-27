# BreatheESG Prototype

ESG data ingestion and analyst review system. Accepts SAP flat file exports, utility portal CSVs, and Concur-style travel JSON. Normalises each into activity records, calculates kgCO2e using pinned DEFRA 2023 factors, and provides an analyst review workflow with a full source-to-calculation audit trail.

## Demo

**Frontend:** http://localhost:5173
**API:** http://localhost:8000/api/v1/

| Email | Password | Organization | State |
|-------|----------|-------------|-------|
| demo@acme.com | demo123 | Acme Corp | 17 green records auto-approved, yellow/red in needs_review |
| analyst@globex.com | demo123 | Globex Corp | All records in ingested / needs_review |
| admin@initech.com | demo123 | Initech Ltd | Same as Globex, admin role |

---

## Local Setup

**Requirements:** Python 3.11+, Node 20+

```bash
git clone <repo>
cd breathe-assigment

# Backend
python -m venv venv
.\venv\Scripts\activate       # Windows
pip install -r backend/requirements.txt

python backend/manage.py migrate
python backend/manage.py loaddata backend/fixtures/emission_factors.json
python backend/manage.py seed_demo

python backend/manage.py runserver 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173, click a demo account to fill credentials, sign in.

---

## Project Structure

```
breathe-assigment/
  backend/
    config/              Django settings, URLs, WSGI
    apps/
      core/              Organization, User, TenantManager
      ingestion/         SourceFile, SourceRow, parsers (SAP/utility/travel), ingestion service
      records/           ActivityRecord, RecordRevision, scopes, units
      emissions/         EmissionFactor, EmissionCalculation
      api/               DRF views, serializers, URL routing
    fixtures/            emission_factors.json (DEFRA 2023)
  frontend/
    src/
      api/               Axios client, TypeScript types, TanStack Query hooks
      store/             Zustand auth store
      pages/             LoginPage, DashboardPage
      components/        LineageDrawer, LockModal, UploadModal, AuditLogTab, Toast
      styles/            tokens.css (Linear design system), globals.css
  fixtures/              Sample data files (SAP CSV, utility CSV, travel JSON)
  MODEL.md               Entity reference and state machine
  DECISIONS.md           9 architectural decision records
  TRADEOFFS.md           3 deliberate tradeoffs with production paths
  SOURCES.md             Emission factor sources and research trail
```

---

## API Reference

All endpoints are under `/api/v1/`. Authentication is JWT (Bearer token in Authorization header).

```
POST   /auth/token/                  Login (returns access + refresh)
POST   /auth/token/refresh/          Refresh access token
GET    /me/                          Current user and org

GET    /source-files/                List ingested files for the org
GET    /source-files/{id}/           File detail

POST   /ingest/sap/                  Upload SAP CSV (multipart)
POST   /ingest/utility/              Upload utility CSV (multipart)
POST   /ingest/travel/               Submit travel JSON (application/json)

GET    /records/                     List activity records (filterable)
GET    /records/{id}/                Record detail
GET    /records/{id}/lineage/        Full source chain including raw payload
GET    /records/{id}/revisions/      Edit history
GET    /records/{id}/calculation/    All emission calculations (current + superseded)
PATCH  /records/{id}/                Update quantity or subcategory (locked records rejected)
POST   /records/bulk-approve/        Approve a list of record IDs
POST   /records/{id}/lock/           Lock a single approved record

GET    /audit-log/                   All RecordRevision rows for the org
```

### Record Filters

`GET /records/` accepts query params: `state`, `quality_tier`, `source_type`, `date_from`, `date_to`, `source_file_id`.

---

## Data Flow

```
Upload file / paste JSON
        |
        v
SHA-256 dedup check (per org)
        |
        v
Parse (SAP / utility / travel parser)
        |
        +-- failed rows --> SourceRow(parse_status=failed, parse_error=...)
        |
        v
Successful rows --> SourceRow(parse_status=ok, raw_payload=...)
        |
        v
Unit normalization + scope assignment
        |
        v
ActivityRecord(state=ingested or needs_review, quality_tier=green/yellow/red)
        |
        v
EmissionFactor lookup (category + date range, DEFRA 2023)
        |
        +-- no factor found --> quality_note NO_FACTOR (red), needs_review
        |
        v
EmissionCalculation(co2e_kg, calculation_notes, is_current=True)
```

---

## Seed Data Edge Cases

The sample fixtures demonstrate every documented edge case:

**SAP (sap_sample.csv)**
| Row | Edge Case | Expected Result |
|-----|-----------|----------------|
| 10 | MENGE missing | UNIT_ASSUMED yellow, stored as L |
| 11 | MEINS = ST (pieces on fuel material) | UNIT_INVALID red, needs_review |
| 12 | MENGE negative, BWART = AB | Rejected: reversal document |
| 13 | WERKS = 1000/01 (multi-company format) | PLANT_AMBIGUOUS yellow |
| Row with PERID = 13 | Year-end adjustment period | Rejected: no calendar month equivalent |

**Utility (utility_sample.csv)**
| Row | Edge Case | Expected Result |
|-----|-----------|----------------|
| 6 | read_type = E (estimated) | ESTIMATED_READ yellow |
| 7 | Billing period crosses month boundary | BILLING_PERIOD_SPLIT yellow |
| 8 | Unit = MWh | Converted to kWh (x 1000) |

**Travel (travel_sample.json)**
| Segment | Edge Case | Expected Result |
|---------|-----------|----------------|
| T001 LHR->DXB | distance_km missing | Haversine calc, DISTANCE_CALCULATED yellow |
| T002 NRT->SIN | Business class | CLASS_FACTOR_NOT_APPLIED yellow |
| T003 car segment | distance_km missing, not applicable | DISTANCE_MISSING red, needs_review |

---

## Documentation

- [MODEL.md](MODEL.md) -- entity descriptions, invariants, state machine
- [DECISIONS.md](DECISIONS.md) -- 9 ADRs (why SE16N, why append-only calculations, etc.)
- [TRADEOFFS.md](TRADEOFFS.md) -- SQLite vs Postgres, economy class factors, Haversine accuracy
- [SOURCES.md](SOURCES.md) -- DEFRA 2023 tables, SAP data elements, OurAirports coordinates

---

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | Django 5.1 + DRF | Mature ORM, migrations, admin, auth |
| Auth | djangorestframework-simplejwt | Standard JWT, works with React |
| Database | SQLite (dev) / PostgreSQL (prod) | `dj-database-url` handles the switch |
| Frontend | React 18 + Vite + TypeScript | Fast dev, type safety |
| State | TanStack Query + Zustand | Query caching + auth state |
| Styling | Vanilla CSS with Linear-inspired design tokens | No build-time CSS tooling, easy to audit |
| Deployment | Railway | PostgreSQL plugin, one-command deploy |
