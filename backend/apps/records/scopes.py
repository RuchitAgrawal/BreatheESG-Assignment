"""
Scope assignment rules.

Prototyped as a code constant. Production path: DB table with org_id
so clients can override (e.g. some orgs classify certain purchased electricity
as Scope 1 under specific PPA structures). Would move to DB with audit trail.
"""

SCOPE_RULES: dict[str, str] = {
    "fuel_diesel":            "1",
    "fuel_petrol":            "1",
    "fuel_lpg":               "1",
    "electricity_grid":       "2",
    "flight_short_haul":      "3",
    "flight_long_haul":       "3",
    "hotel_stay":             "3",
    "ground_transport_car":   "3",
    "ground_transport_rail":  "3",
}


def get_scope(category: str) -> str:
    return SCOPE_RULES.get(category, "3")
