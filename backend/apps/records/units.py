"""
Unit normalization.

MVP: hardcoded dict of 5 conversion pairs.
Production path: pint library with a per-client unit master table.
Some clients report in short tons, some in metric tons -- cannot assume
without a master. Pint also handles temperature and volume edge cases
(fluid ounces vs weight ounces) that this dict cannot.
"""
from decimal import Decimal


# Canonical unit per category -- what we normalize everything into
CANONICAL_UNITS: dict[str, str] = {
    "fuel_diesel":            "L",
    "fuel_petrol":            "L",
    "fuel_lpg":               "L",
    "electricity_grid":       "kWh",
    "flight_short_haul":      "km",
    "flight_long_haul":       "km",
    "hotel_stay":             "night",
    "ground_transport_car":   "km",
    "ground_transport_rail":  "km",
}

# Conversion factors: multiply quantity in FROM unit to get TO unit
UNIT_CONVERSIONS: dict[tuple[str, str], Decimal] = {
    ("gal", "L"):                Decimal("3.78541"),
    ("mi", "km"):                Decimal("1.60934"),
    ("lb", "kg"):                Decimal("0.453592"),
    ("kWh", "MWh"):              Decimal("0.001"),
    ("MWh", "kWh"):              Decimal("1000"),
    ("short_ton", "metric_ton"): Decimal("0.907185"),
    ("t", "metric_ton"):         Decimal("1"),
    ("kg", "L"):                 Decimal("1"),  # approximate for diesel/petrol
}


def normalize_quantity(
    quantity: Decimal, from_unit: str, category: str
) -> tuple[Decimal, str]:
    """
    Returns (normalized_quantity, canonical_unit).
    If no conversion is available, returns the original quantity and unit
    with a note that manual review is needed.
    """
    canonical = CANONICAL_UNITS.get(category, from_unit)

    if from_unit == canonical:
        return quantity, canonical

    key = (from_unit, canonical)
    if key in UNIT_CONVERSIONS:
        return quantity * UNIT_CONVERSIONS[key], canonical

    # No conversion -- return as-is, caller should flag for review
    return quantity, from_unit


def assign_quality_tier(quality_notes: list[dict]) -> str:
    """
    Derive quality tier from the severity of the worst quality note.
    Rules are in code (not DB) so they are testable and easy to change.
    """
    severities = {n.get("severity") for n in quality_notes}
    if "red" in severities:
        return "red"
    if "yellow" in severities:
        return "yellow"
    return "green"


def assign_state_from_quality(quality_tier: str) -> str:
    """Clean records go straight to approved; flagged ones need review."""
    if quality_tier == "green":
        return "ingested"   # will auto-approve in seed; in prod analyst approves
    return "needs_review"
