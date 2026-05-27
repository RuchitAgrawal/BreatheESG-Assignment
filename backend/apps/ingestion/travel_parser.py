"""
Corporate travel JSON parser (Concur-like format).

Format decision: JSON paste via textarea (not API pull).
Concur API requires OAuth client credentials + IT provisioning per client.
For a prototype, the realistic path is: analyst exports a JSON travel report from
Concur, copies the payload, pastes it into our tool. Same data, zero integration overhead.
Navan, TripActions, and similar platforms offer similar export functionality.

Documented edge cases in sample data:
- Segment 2 (LHR->DXB): distance_km missing -> great-circle calc, DISTANCE_CALCULATED (yellow)
- Trip 3 Car segment: distance_km missing, airports not applicable -> DISTANCE_MISSING (red)
- Hotel segment: handled separately (unit = nights, not km)

DEFRA 2023 short/long haul boundary: 3,700 km
Source: DEFRA Greenhouse Gas Reporting: Conversion Factors 2023, Table 10

Airport coordinate set: 20 major hubs covering ~80% of corporate business travel.
Full IATA database = 9,000+ records; maintenance burden out of scope for prototype.
Production path: integrate OurAirports dataset (CSV, ~7,000 records, CC0 license)
or airport reference API with caching.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from math import radians, cos, sin, asin, sqrt
from typing import Optional


# 20 major airports: IATA code -> (lat, lon)
# Source: official airport coordinates, publicly available
AIRPORT_COORDS: dict[str, tuple[float, float]] = {
    "SFO": (37.6213, -122.3790),
    "JFK": (40.6413, -73.7781),
    "LAX": (33.9425, -118.4081),
    "ORD": (41.9742, -87.9073),
    "YYZ": (43.6777, -79.6248),
    "LHR": (51.4775, -0.4614),
    "CDG": (49.0097, 2.5479),
    "FRA": (50.0379, 8.5622),
    "AMS": (52.3086, 4.7639),
    "DXB": (25.2532, 55.3657),
    "SIN": (1.3644, 103.9915),
    "HKG": (22.3080, 113.9185),
    "NRT": (35.7720, 140.3929),
    "ICN": (37.4602, 126.4407),
    "PEK": (40.0799, 116.6031),
    "BOM": (19.0896, 72.8656),
    "DEL": (28.5562, 77.1000),
    "SYD": (-33.9461, 151.1772),
    "GRU": (-23.4356, -46.4731),
    "MEX": (19.4363, -99.0721),
}

# DEFRA 2023 boundary between short-haul and long-haul (km)
DEFRA_SHORT_HAUL_LIMIT_KM = 3700


@dataclass
class SegmentResult:
    status: str
    error: str = ""
    trip_id: str = ""
    traveler_email: str = ""
    segment_index: int = 0
    activity_date: Optional[date] = None
    category: str = ""
    quantity: Optional[Decimal] = None
    unit: str = ""
    subcategory: str = ""
    quality_notes: list = field(default_factory=list)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Haversine great-circle distance in km.
    Uses mean Earth radius 6,371 km. Accurate to within ~0.5% for long-haul routes.
    Note: does not use WGS84 ellipsoid -- production path would use geopy or similar.
    """
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def great_circle_km(departure: str, arrival: str) -> Optional[float]:
    dep = departure.upper().strip()
    arr = arrival.upper().strip()
    if dep not in AIRPORT_COORDS or arr not in AIRPORT_COORDS:
        return None
    lat1, lon1 = AIRPORT_COORDS[dep]
    lat2, lon2 = AIRPORT_COORDS[arr]
    return haversine_km(lat1, lon1, lat2, lon2)


def parse_date(raw: str) -> date:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: '{raw}'")


def parse_flight_segment(seg: dict, trip_id: str, traveler: str, seg_idx: int) -> SegmentResult:
    notes = []

    dep = seg.get("departure_airport", seg.get("from", "")).upper().strip()
    arr = seg.get("arrival_airport", seg.get("to", "")).upper().strip()
    raw_date = seg.get("departure_date", seg.get("date", ""))

    if not dep or not arr:
        return SegmentResult(
            status="failed",
            error="departure_airport or arrival_airport is missing.",
            trip_id=trip_id,
        )

    try:
        activity_date = parse_date(raw_date) if raw_date else None
    except ValueError as e:
        return SegmentResult(status="failed", error=str(e), trip_id=trip_id)

    # -- Distance -------------------------------------------------------------
    distance_km = seg.get("distance_km")
    if distance_km is None:
        calc = great_circle_km(dep, arr)
        if calc is None:
            return SegmentResult(
                status="failed",
                error=(
                    f"Unknown airport code(s): '{dep}' or '{arr}'. "
                    "Not in the 20-airport hardcoded set. "
                    "Production path: full IATA database or OurAirports integration."
                ),
                trip_id=trip_id,
            )
        distance_km = round(calc, 1)
        notes.append({
            "code": "DISTANCE_CALCULATED",
            "severity": "yellow",
            "message": (
                f"distance_km not provided for {dep}->{arr}. "
                f"Calculated via Haversine great-circle: {distance_km} km. "
                "Haversine uses mean Earth radius (6,371 km), accurate to ~0.5% for long-haul. "
                "Actual flight distance may vary by routing (not straight line)."
            ),
        })
    else:
        distance_km = float(distance_km)

    # -- Short vs long haul (DEFRA 2023 boundary at 3,700 km) ----------------
    category = "flight_short_haul" if distance_km < DEFRA_SHORT_HAUL_LIMIT_KM else "flight_long_haul"

    travel_class = seg.get("class", seg.get("cabin_class", "economy")).lower()
    # Note: DEFRA applies class multipliers (business ~2.9x economy for long-haul)
    # We use economy factor for all classes for prototype simplicity.
    # This is an open question documented in DECISIONS.md.
    if travel_class not in ("economy", ""):
        notes.append({
            "code": "CLASS_FACTOR_NOT_APPLIED",
            "severity": "yellow",
            "message": (
                f"Travel class '{travel_class}' recorded but class-specific emission factors not implemented. "
                "DEFRA 2023 business class long-haul factor is ~2.9x economy. "
                "Economy factor applied. Document as known limitation."
            ),
        })

    subcategory = f"{dep}->{arr} | {travel_class} | {dep} {'(calc)' if 'DISTANCE_CALCULATED' in str([n['code'] for n in notes]) else '(provided)'}"

    return SegmentResult(
        status="ok",
        trip_id=trip_id,
        traveler_email=traveler,
        segment_index=seg_idx,
        activity_date=activity_date,
        category=category,
        quantity=Decimal(str(distance_km)),
        unit="km",
        subcategory=subcategory,
        quality_notes=notes,
    )


def parse_hotel_segment(seg: dict, trip_id: str, traveler: str, seg_idx: int) -> SegmentResult:
    notes = []
    raw_date = seg.get("check_in", seg.get("date", ""))
    try:
        activity_date = parse_date(raw_date) if raw_date else None
    except ValueError as e:
        return SegmentResult(status="failed", error=str(e), trip_id=trip_id)

    nights = seg.get("nights", seg.get("duration_nights", 1))
    city = seg.get("city", seg.get("location", ""))
    hotel_name = seg.get("hotel_name", seg.get("property", ""))

    return SegmentResult(
        status="ok",
        trip_id=trip_id,
        traveler_email=traveler,
        segment_index=seg_idx,
        activity_date=activity_date,
        category="hotel_stay",
        quantity=Decimal(str(nights)),
        unit="night",
        subcategory=f"{hotel_name} | {city}".strip(" |"),
        quality_notes=notes,
    )


def parse_ground_segment(seg: dict, trip_id: str, traveler: str, seg_idx: int) -> SegmentResult:
    notes = []
    raw_date = seg.get("date", seg.get("pickup_date", ""))
    try:
        activity_date = parse_date(raw_date) if raw_date else None
    except ValueError as e:
        return SegmentResult(status="failed", error=str(e), trip_id=trip_id)

    distance_km = seg.get("distance_km")
    transport_type = seg.get("transport_type", seg.get("mode", "car")).lower()
    category = "ground_transport_rail" if "rail" in transport_type or "train" in transport_type \
               else "ground_transport_car"

    if distance_km is None:
        notes.append({
            "code": "DISTANCE_MISSING",
            "severity": "red",
            "message": (
                "distance_km not provided for ground transport segment. "
                "Great-circle calc not applicable (ground routes are not straight lines). "
                "Needs human review to enter actual distance."
            ),
        })
        distance_km = 0

    city_from = seg.get("pickup_location", seg.get("from", ""))
    city_to = seg.get("dropoff_location", seg.get("to", ""))

    return SegmentResult(
        status="ok" if float(distance_km) > 0 else "ok",  # keep as ok, let quality tier handle
        trip_id=trip_id,
        traveler_email=traveler,
        segment_index=seg_idx,
        activity_date=activity_date,
        category=category,
        quantity=Decimal(str(distance_km)),
        unit="km",
        subcategory=f"{city_from} -> {city_to}".strip(" ->"),
        quality_notes=notes,
    )


def parse_travel_json(payload: dict) -> list[SegmentResult]:
    """
    Parse a Concur-like travel report JSON.
    Returns one SegmentResult per trip segment (flights, hotels, ground transport).
    """
    results = []

    trips = payload.get("trips", payload.get("Trips", []))
    if not trips:
        # Some exports wrap in a 'data' key
        trips = payload.get("data", {}).get("trips", [])

    for trip in trips:
        trip_id = str(trip.get("trip_id", trip.get("TripId", "")))
        traveler = trip.get("traveler_email", trip.get("travelerEmail", ""))
        segments = trip.get("segments", trip.get("Segments", []))

        for seg_idx, seg in enumerate(segments, start=1):
            seg_type = seg.get("type", seg.get("Type", "flight")).lower()

            if seg_type in ("flight", "air"):
                result = parse_flight_segment(seg, trip_id, traveler, seg_idx)
            elif seg_type in ("hotel", "accommodation", "lodging"):
                result = parse_hotel_segment(seg, trip_id, traveler, seg_idx)
            elif seg_type in ("car", "ground", "rail", "train", "taxi", "ride"):
                result = parse_ground_segment(seg, trip_id, traveler, seg_idx)
            else:
                result = SegmentResult(
                    status="failed",
                    trip_id=trip_id,
                    error=f"Unknown segment type '{seg_type}'. Supported: flight, hotel, car, rail.",
                )

            results.append(result)

    return results
