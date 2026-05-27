"""
Utility portal CSV parser.

Format decision: Portal CSV export (Dominion Energy / UK Power Networks format).
PDF bill parsing requires OCR with provider-specific layout training -- out of scope.
GreenButton API requires OAuth + utility provider partnership.
Portal CSV is what facilities teams actually do: log in, select date range, export.

Documented edge cases in sample data:
- Row 6: read_type = 'E' (estimated, not actual) -> ESTIMATED_READ (yellow)
- Row 7: Billing period Dec 10 - Jan 9 (crosses month boundary) -> BILLING_PERIOD_SPLIT (yellow)
- Row 8: unit = 'MWh' instead of 'kWh' -> unit conversion applied, green

Known production failure modes:
- Multiple meters in one file with different tariff structures
- Bill period > 31 days (quarterly billing)
- Reactive power (kVAR) rows mixed in with active power (kWh)
- Demand charges (kW, not kWh) in the same export
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional
import calendar


@dataclass
class ParseResult:
    status: str
    error: str = ""
    activity_date: Optional[date] = None   # billing_period_start used as the record date
    billing_period_start: Optional[date] = None
    billing_period_end: Optional[date] = None
    category: str = "electricity_grid"
    quantity: Optional[Decimal] = None
    unit: str = "kWh"
    subcategory: str = ""
    quality_notes: list = field(default_factory=list)


def parse_date(raw: str) -> date:
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: '{raw}'")


def parse_utility_row(row: dict, row_index: int) -> ParseResult:
    notes = []

    # -- Billing period -------------------------------------------------------
    raw_start = row.get("billing_period_start", row.get("start_date", "")).strip()
    raw_end = row.get("billing_period_end", row.get("end_date", "")).strip()

    if not raw_start or not raw_end:
        return ParseResult(
            status="failed",
            error="billing_period_start or billing_period_end is missing.",
        )
    try:
        period_start = parse_date(raw_start)
        period_end = parse_date(raw_end)
    except ValueError as e:
        return ParseResult(status="failed", error=str(e))

    if period_end < period_start:
        return ParseResult(
            status="failed",
            error=f"billing_period_end ({period_end}) is before billing_period_start ({period_start}).",
        )

    # -- Estimated read -------------------------------------------------------
    read_type = row.get("read_type", row.get("ReadType", "A")).strip().upper()
    if read_type.startswith("E"):
        notes.append({
            "code": "ESTIMATED_READ",
            "severity": "yellow",
            "message": (
                f"Meter read type '{read_type}' indicates an estimated reading, not an actual meter read. "
                "Actual reads are typically received 1-4 weeks later. "
                "Policy question: should estimated reads be lockable for audit, "
                "or always held as needs_review until actual read arrives?"
            ),
        })

    # -- Cross-month billing period -------------------------------------------
    if period_start.month != period_end.month or period_start.year != period_end.year:
        days_total = (period_end - period_start).days + 1
        # Days in the first month
        if period_start.month == 12:
            next_month_start = date(period_start.year + 1, 1, 1)
        else:
            next_month_start = date(period_start.year, period_start.month + 1, 1)
        days_month1 = (next_month_start - period_start).days
        days_month2 = days_total - days_month1
        notes.append({
            "code": "BILLING_PERIOD_SPLIT",
            "severity": "yellow",
            "message": (
                f"Billing period {period_start} to {period_end} crosses a month boundary. "
                f"Pro-rata allocation (by days): "
                f"{days_month1} days in {period_start.strftime('%b %Y')}, "
                f"{days_month2} days in {period_end.strftime('%b %Y')}. "
                "Known limitation: pro-rata is incorrect for fixed charges vs variable charges. "
                "Production path: split into two ActivityRecords, one per calendar month."
            ),
        })

    # -- Quantity -------------------------------------------------------------
    raw_qty = row.get("quantity", row.get("Quantity", row.get("consumption", ""))).strip()
    if not raw_qty:
        return ParseResult(status="failed", error="quantity is missing.")
    try:
        quantity = Decimal(raw_qty.replace(",", ""))
    except InvalidOperation:
        return ParseResult(status="failed", error=f"quantity '{raw_qty}' is not a valid number.")

    if quantity <= 0:
        return ParseResult(status="failed", error=f"quantity {quantity} is zero or negative.")

    # -- Unit -----------------------------------------------------------------
    unit = row.get("unit", row.get("Unit", "kWh")).strip()

    meter_id = row.get("meter_id", row.get("MeterID", row.get("meter", ""))).strip()
    tariff = row.get("tariff_code", row.get("TariffCode", "")).strip()
    subcategory = f"meter:{meter_id}" + (f" tariff:{tariff}" if tariff else "")

    return ParseResult(
        status="ok",
        activity_date=period_start,
        billing_period_start=period_start,
        billing_period_end=period_end,
        category="electricity_grid",
        quantity=quantity,
        unit=unit,
        subcategory=subcategory,
        quality_notes=notes,
    )


def parse_utility_csv(content: bytes) -> list[ParseResult]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    results = []
    for i, row in enumerate(reader, start=1):
        results.append(parse_utility_row(row, i))
    return results
