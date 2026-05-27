# Sample Fixtures

These files are used by `python manage.py seed_demo` to seed three demo organizations. Each file was constructed to exercise a specific set of edge cases documented in the parsers.

---

## sap_sample.csv

SAP SE16N flat file export format. 12 data rows, 2 of which are intentionally rejected.

```
EBELN,EBELP,MATNR,MENGE,MEINS,WERKS,BUDAT,BWART
4500001234,10,DIESEL-001,500,L,1000,20241101,101   <- row 1: clean diesel, green
4500001234,20,DIESEL-001,320,L,1000,20241108,101   <- row 2: clean diesel, green
4500001235,10,DIESEL-002,1200,L,2000,20241115,101  <- row 3: large quantity, different plant
4500001236,10,PETROL-001,250,L,1000,20241118,101   <- row 4: petrol material
4500001237,10,DIESEL-003,890,L,3000,20241122,101   <- row 5: third plant
4500001238,10,LPG-001,400,KG,2000,20241125,101     <- row 6: LPG in KG, UNIT_NOT_NORMALIZED yellow
4500001239,10,DIESEL-004,760,L,1000,20241128,101   <- row 7: clean diesel
4500001240,10,PETROL-002,310,L,3000,20241130,101   <- row 8: petrol, third plant
4500001241,10,DIESEL-005,,L,1000,20241201,101      <- row 9: MENGE empty, UNIT_ASSUMED yellow
4500001242,10,DIESEL-006,200,ST,2000,20241203,101  <- row 10: MEINS=ST (pieces), UNIT_INVALID red
4500001243,10,DIESEL-007,-150,L,1000,20241205,AB   <- row 11: REJECTED reversal (BWART=AB, MENGE<0)
4500001244,10,DIESEL-008,600,L,1000/01,20241210,101 <- row 12: WERKS ambiguous, PLANT_AMBIGUOUS yellow
```

**Row 9 (DIESEL-005):** `MENGE` is empty. The parser assumes 0 and rejects with "MENGE is zero". Actually no -- the CSV field is blank, `strip()` gives empty string, `Decimal("")` raises `InvalidOperation`. Caught and stored as parse_error. Wait -- actually looking at the parser: `raw_menge = row.get("MENGE", "0").strip()` so blank MENGE -> "0" -> `Decimal("0")` -> rejected as "MENGE is zero". Stored as failed SourceRow.

**Row 11 (DIESEL-007):** `BWART=AB` and `MENGE=-150`. Both conditions independently trigger rejection. The parser checks `bwart in REVERSAL_TYPES` first.

**Row 12 (DIESEL-008):** `WERKS=1000/01` contains a slash, which the parser uses as a heuristic for the multi-company-code format (BUKRS/WERKS). This is flagged yellow but not rejected -- the record is stored and can be approved after analyst review.

**Result after ingestion:** 10 accepted rows, 2 rejected rows (rows 11 and 12 in 1-indexed, i.e. the reversal and the zero-quantity row). The 10 accepted rows include some yellow (LPG in KG, plant ambiguous) and some green.

---

## utility_sample.csv

```
meter_id,billing_period_start,billing_period_end,quantity,unit,read_type,tariff_code
MTR-001,2024-10-01,2024-10-31,12540,kWh,A,TOU-D    <- row 1: clean, green
MTR-001,2024-11-01,2024-11-30,13820,kWh,A,TOU-D    <- row 2: clean, green
MTR-002,2024-10-01,2024-10-31,8430,kWh,A,SME-1     <- row 3: second meter, green
MTR-002,2024-11-01,2024-11-30,9120,kWh,A,SME-1     <- row 4: clean, green
MTR-001,2024-09-01,2024-09-30,11250,kWh,A,TOU-D    <- row 5: September, green
MTR-002,2024-12-01,2024-12-31,7890,kWh,E,SME-1     <- row 6: read_type=E estimated, yellow
MTR-001,2024-12-10,2025-01-09,14200,kWh,A,TOU-D    <- row 7: crosses Dec/Jan boundary, yellow
MTR-003,2024-11-01,2024-11-30,5.2,MWh,A,HV-2       <- row 8: unit=MWh, converted to 5200 kWh
```

**Row 6:** `read_type=E`. ESTIMATED_READ yellow note. Record moves to needs_review. Analyst should update once the actual read arrives.

**Row 7:** `billing_period_start=2024-12-10`, `billing_period_end=2025-01-09`. Crosses a month boundary. The parser calculates the pro-rata split (22 days in December, 9 days in January) and logs it as a BILLING_PERIOD_SPLIT yellow note. The record is stored against 2024-12-10 as the activity_date. Production path: split into two ActivityRecords, one per calendar month.

**Row 8:** `unit=MWh`. The unit conversion in `units.py` converts 5.2 MWh to 5200 kWh using the `("MWh", "kWh")` conversion factor. The result is stored as `normalized_quantity=5200, normalized_unit=kWh`. This is a green record.

All 8 rows are accepted (none rejected). 5 green, 2 yellow, 1 green (MWh -> kWh).

---

## travel_sample.json

Three trips, seven segments.

**Trip T001 (john.smith@acme.com)**

- Segment 1: SFO -> LHR, economy, `distance_km=8629` provided. Long-haul (> 3700 km). Green. CO2e: 8629 * 0.195 = 1682.7 kgCO2e.
- Segment 2: LHR -> DXB, economy, no `distance_km`. Haversine calculates 5484 km. Long-haul. DISTANCE_CALCULATED yellow. CO2e: 5484 * 0.195 = 1069.4 kgCO2e.
- Segment 3: Hotel, Dubai, 2 nights. Green. CO2e: 2 * 36 = 72 kgCO2e.

**Trip T002 (sarah.jones@acme.com)**

- Segment 1: JFK -> BOS, economy, `distance_km=299`. Short-haul (< 3700 km). Green. CO2e: 299 * 0.2552 = 76.3 kgCO2e.
- Segment 2: NRT -> SIN, business class, no `distance_km`. Haversine: 5315 km. Long-haul. Two notes: DISTANCE_CALCULATED (yellow) and CLASS_FACTOR_NOT_APPLIED (yellow). Economy factor applied: 5315 * 0.195 = 1036.4 kgCO2e. Actual business class CO2e would be ~2.2x higher.

**Trip T003 (amit.patel@acme.com)**

- Segment 1: CDG -> AMS, economy, `distance_km=430`. Short-haul. Green. CO2e: 430 * 0.2552 = 109.7 kgCO2e.
- Segment 2: Car, Amsterdam Airport -> Amsterdam City Centre, no `distance_km`, `transport_type=car`. DISTANCE_MISSING red. CO2e: 0 (no calculation until analyst enters distance).

**Result after ingestion:** 7 segments accepted, 0 rejected. Quality mix: 3 green, 3 yellow, 1 red.
