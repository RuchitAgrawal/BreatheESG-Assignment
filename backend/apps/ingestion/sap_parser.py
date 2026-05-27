"""
SAP SE16N flat file CSV parser.

Format decision: SE16N transaction export via SFTP.
IDoc requires SAP middleware + vendor pre-registration in WE20.
OData needs SAP Gateway + OAuth setup -- rare for external vendors without deep integration.
BAPI_PO_GETITEMS requires pre-provisioned RFC credentials.
SE16N flat file = politically realistic for quarterly ESG bulk pulls.

Documented edge cases in sample data:
- Row 9:  MEINS missing -> unit assumed 'L', flagged UNIT_ASSUMED (yellow)
- Row 10: MEINS = 'ST' (Stueck/pieces) on fuel -> UNIT_INVALID (red)
- Row 11: BWART = 'AB', negative MENGE -> reversal doc, parse failed
- Row 12: WERKS = '1000/01' -> multi-company format, PLANT_AMBIGUOUS (yellow)
- Row 13: Period 13 posting -> year-end adjustment, parse failed
- Row 14: German column headers -> normalized before parsing
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Optional

# Maps German-locale SE16N column labels to canonical SAP internal names.
# Source: SAP EKPO/EKKO data element documentation (SE11 transaction).
# Covers common German overrides. French/Spanish locale is production-path work
# requiring per-client locale config.
GERMAN_HEADER_MAP: dict[str, str] = {
    "Einkaufsbelegnummer":  "EBELN",
    "Position":             "EBELP",
    "Materialnummer":       "MATNR",
    "Menge":                "MENGE",
    "Mengeneinheit":        "MEINS",
    "Werk":                 "WERKS",
    "Buchungsdatum":        "BUDAT",
    "Bewegungsart":         "BWART",
    "Buchungsperiode":      "PERID",
    # Common aliases seen in mixed-locale exports
    "Quantity":             "MENGE",
    "Unit":                 "MEINS",
    "Plant":                "WERKS",
    "Posting Date":         "BUDAT",
    "Movement Type":        "BWART",
    "Material":             "MATNR",
    "PO Number":            "EBELN",
    "Item":                 "EBELP",
}

# SAP material number prefixes that indicate fuel materials
FUEL_MATNR_PREFIXES = ("FUEL", "DIES", "PETR", "LPG", "GAS", "OIL")

REVERSAL_TYPES = {"102", "122", "AB", "STORNO"}


@dataclass
class ParseResult:
    status: str          # "ok" or "failed"
    error: str = ""
    activity_date: Optional[date] = None
    category: str = ""
    quantity: Optional[Decimal] = None
    unit: str = ""
    subcategory: str = ""
    quality_notes: list = field(default_factory=list)


def normalize_headers(raw_headers: list[str]) -> list[str]:
    """Map German or alias headers to canonical SAP field names."""
    return [GERMAN_HEADER_MAP.get(h.strip(), h.strip()) for h in raw_headers]


def parse_sap_date(raw: str) -> date:
    """
    SAP exports dates in YYYYMMDD or DD.MM.YYYY depending on system locale config.
    Try both -- raise ValueError with the raw value if neither matches.
    """
    raw = raw.strip()
    for fmt in ("%Y%m%d", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized SAP date format: '{raw}' (tried YYYYMMDD and DD.MM.YYYY)")


def guess_fuel_category(matnr: str) -> str:
    """Infer category from material number prefix when explicit type not present."""
    matnr = (matnr or "").upper()
    if any(matnr.startswith(p) for p in ("LPG", "PROP")):
        return "fuel_lpg"
    if any(matnr.startswith(p) for p in ("PETR", "UNL", "PET")):
        return "fuel_petrol"
    return "fuel_diesel"  # default for fuel materials


def parse_sap_row(row: dict, row_index: int) -> ParseResult:
    notes = []

    # -- Date ------------------------------------------------------------------
    raw_date = row.get("BUDAT", "").strip()
    if not raw_date:
        return ParseResult(status="failed", error="BUDAT (posting date) is missing.")
    try:
        activity_date = parse_sap_date(raw_date)
    except ValueError as e:
        return ParseResult(status="failed", error=str(e))

    # -- Period 13+ (year-end adjustments) ------------------------------------
    # PERID not always present in SE16N exports; only check if present.
    perid = row.get("PERID", "").strip()
    if perid:
        try:
            if int(perid) > 12:
                return ParseResult(
                    status="failed",
                    error=(
                        f"SAP posting period {perid} is a year-end adjustment period "
                        "(Periode 13-16 have no calendar month equivalent). "
                        "Cannot map to a reporting month. "
                        "Production path: allocate to Dec 31 with analyst flag, "
                        "or exclude per client ESG reporting policy."
                    ),
                )
        except ValueError:
            pass  # non-numeric PERID is unusual, skip check

    # -- Reversal documents ---------------------------------------------------
    bwart = row.get("BWART", "").strip().upper()
    raw_menge = row.get("MENGE", "0").strip().replace(",", ".")
    try:
        menge = Decimal(raw_menge)
    except InvalidOperation:
        return ParseResult(status="failed", error=f"MENGE '{raw_menge}' is not a valid number.")

    if bwart in REVERSAL_TYPES or menge < 0:
        return ParseResult(
            status="failed",
            error=(
                f"Reversal document detected (BWART='{bwart}', MENGE={menge}). "
                "Rejected at ingestion. "
                "Production path: net reversal against original PO line, or keep in a "
                "separate reversal ledger and reconcile at period-end."
            ),
        )

    if menge == 0:
        return ParseResult(status="failed", error="MENGE is zero; skipping zero-quantity row.")

    # -- Unit (MEINS) ---------------------------------------------------------
    meins = row.get("MEINS", "").strip()
    if not meins:
        meins = "L"
        notes.append({
            "code": "UNIT_ASSUMED",
            "severity": "yellow",
            "message": (
                "MEINS (unit of measure) is missing. "
                "Assumed 'L' (litres) based on fuel material type. "
                "Verify with client -- incorrect unit will produce wrong CO2e."
            ),
        })
    elif meins == "ST":
        # Stueck = pieces in German -- wrong unit for a fuel material
        notes.append({
            "code": "UNIT_INVALID",
            "severity": "red",
            "message": (
                "MEINS = 'ST' (Stueck, meaning pieces/units) on a fuel material. "
                "Cannot convert pieces to litres without a material-specific conversion factor. "
                "Needs human review before this record can be approved."
            ),
        })

    # -- Plant code (WERKS) ---------------------------------------------------
    werks = row.get("WERKS", "").strip()
    if "/" in werks:
        notes.append({
            "code": "PLANT_AMBIGUOUS",
            "severity": "yellow",
            "message": (
                f"WERKS '{werks}' appears to use multi-company format (BUKRS/WERKS). "
                "Cannot disambiguate plant without a company-code lookup table. "
                "Production path: lookup table mapping plant code to legal entity."
            ),
        })

    # -- Category from material number ----------------------------------------
    matnr = row.get("MATNR", "").strip()
    category = guess_fuel_category(matnr)
    subcategory = f"MATNR:{matnr} WERKS:{werks}" if matnr else f"WERKS:{werks}"

    return ParseResult(
        status="ok",
        activity_date=activity_date,
        category=category,
        quantity=menge,
        unit=meins,
        subcategory=subcategory,
        quality_notes=notes,
    )


def parse_sap_csv(content: bytes) -> list[ParseResult]:
    """
    Parse the full SAP CSV file.
    Returns one ParseResult per row (including failed ones).
    """
    text = content.decode("utf-8-sig")  # handle BOM from Windows SAP exports
    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        return []

    # Normalize headers before processing any rows
    normalized_fieldnames = normalize_headers(list(reader.fieldnames))
    reader.fieldnames = normalized_fieldnames

    results = []
    for i, row in enumerate(reader, start=1):
        results.append(parse_sap_row(row, i))
    return results
