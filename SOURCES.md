# Sources

Emission factors and reference data used in this system. Each entry includes what was used, where it was found, and what was extracted.

---

## 1. DEFRA Greenhouse Gas Reporting: Conversion Factors 2023

**URL:** https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2023

**Used for:** All nine emission factors in `backend/fixtures/emission_factors.json`

**What was extracted**

| Category | Factor | Unit | Table |
|----------|--------|------|-------|
| Diesel (average biofuel blend) | 2.5164 kgCO2e/L | L | Table 3 |
| Petrol (average biofuel blend) | 2.1682 kgCO2e/L | L | Table 3 |
| LPG | 1.5549 kgCO2e/L | L | Table 3 |
| UK grid electricity | 0.20729 kgCO2e/kWh | kWh | Table 12 |
| Short-haul flight, economy | 0.2552 kgCO2e/km | km | Table 10 |
| Long-haul flight, economy | 0.1950 kgCO2e/km | km | Table 10 |
| Hotel stay | 36.0 kgCO2e/night | night | Table 16 |
| Car (average, market mix) | 0.1704 kgCO2e/km | km | Table 5 |
| Rail (national average) | 0.0353 kgCO2e/km | km | Table 5 |

**Short vs long haul boundary:** 3,700 km, from Table 10 footnotes.

**Radiative forcing index (RFI):** DEFRA 2023 recommends an uplift factor of 1.891 for long-haul aviation to account for non-CO2 effects (contrails, ozone, water vapour). This prototype does not apply RFI -- see TRADEOFFS.md Tradeoff 3.

**Notes on the electricity factor**

The UK grid factor of 0.20729 kgCO2e/kWh is the annual average for 2023. It includes transmission and distribution losses. It does not apply to renewable energy certificates (RECs) or Power Purchase Agreements (PPAs), where the contractual allocation of zero-carbon generation would justify using a market-based factor. This distinction (location-based vs market-based Scope 2) is not implemented in this prototype.

---

## 2. SAP Data Element Documentation (SE11 / ABAP Dictionary)

**URL:** https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE (search for data elements EBELN, EBELP, MEINS, BWART, WERKS, BUDAT, PERID)

**Used for:** German-to-English header mapping in `backend/apps/ingestion/sap_parser.py`

**What was extracted**

The `GERMAN_HEADER_MAP` dict maps German SE16N column labels to their canonical SAP field names:

| German label | SAP field | Meaning |
|-------------|-----------|---------|
| Einkaufsbelegnummer | EBELN | Purchase order number |
| Position | EBELP | PO line item number |
| Materialnummer | MATNR | Material number |
| Menge | MENGE | Quantity |
| Mengeneinheit | MEINS | Unit of measure |
| Werk | WERKS | Plant code |
| Buchungsdatum | BUDAT | Posting date (YYYYMMDD or DD.MM.YYYY) |
| Bewegungsart | BWART | Movement type |
| Buchungsperiode | PERID | Posting period (1-16; periods 13-16 are year-end adjustments) |

**SAP period 13 and beyond**

SAP fiscal years support up to 16 posting periods. Periods 13-16 are year-end adjustment periods with no direct calendar month equivalent. They are used for year-end accruals, audit adjustments, and statutory postings. This parser rejects rows with `PERID > 12` with an explicit error message explaining the ambiguity. The production path is a client-level policy: either allocate to December 31 or exclude from ESG reporting.

**Reversal movement types**

Movement type `BWART` codes `102`, `122`, and `AB` (and any negative `MENGE`) indicate reversal documents in standard SAP. A reversal does not represent a physical goods receipt; it cancels a prior posting. These rows are rejected at ingestion. The production path for high-volume clients is net reversal against the original PO line during period-end reconciliation.

---

## 3. OurAirports Dataset

**URL:** https://ourairports.com/data/

**Used for:** Airport coordinate reference for Haversine distance calculation in `backend/apps/ingestion/travel_parser.py`

**What was extracted**

Coordinates for 20 major international airports (IATA code, latitude, longitude). The full OurAirports dataset contains approximately 7,000 airports and is available under the public domain (CC0). The 20-airport subset covers the most frequent origin and destination cities in corporate business travel.

The coordinates used are:

| IATA | Airport | Lat | Lon |
|------|---------|-----|-----|
| SFO | San Francisco International | 37.6213 | -122.3790 |
| JFK | John F. Kennedy International | 40.6413 | -73.7781 |
| LAX | Los Angeles International | 33.9425 | -118.4081 |
| ORD | Chicago O'Hare | 41.9742 | -87.9073 |
| YYZ | Toronto Pearson | 43.6777 | -79.6248 |
| LHR | London Heathrow | 51.4775 | -0.4614 |
| CDG | Paris Charles de Gaulle | 49.0097 | 2.5479 |
| FRA | Frankfurt | 50.0379 | 8.5622 |
| AMS | Amsterdam Schiphol | 52.3086 | 4.7639 |
| DXB | Dubai International | 25.2532 | 55.3657 |
| SIN | Singapore Changi | 1.3644 | 103.9915 |
| HKG | Hong Kong International | 22.3080 | 113.9185 |
| NRT | Tokyo Narita | 35.7720 | 140.3929 |
| ICN | Seoul Incheon | 37.4602 | 126.4407 |
| PEK | Beijing Capital | 40.0799 | 116.6031 |
| BOM | Mumbai Chhatrapati Shivaji | 19.0896 | 72.8656 |
| DEL | Delhi Indira Gandhi | 28.5562 | 77.1000 |
| SYD | Sydney Kingsford Smith | -33.9461 | 151.1772 |
| GRU | Sao Paulo Guarulhos | -23.4356 | -46.4731 |
| MEX | Mexico City International | 19.4363 | -99.0721 |

**Haversine formula accuracy**

The Haversine formula uses a mean Earth radius of 6,371 km. The maximum error vs WGS84 ellipsoid is approximately 0.3% for polar routes, less than 0.1% for equatorial routes. For a 10,000 km flight, the maximum absolute error is about 30 km, which translates to approximately 5.9 kgCO2e at the economy long-haul factor. This is within acceptable bounds for a Scope 3 estimation where the dominant source of uncertainty is the emission factor itself (which varies year to year and by methodology).
