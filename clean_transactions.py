"""
clean_transactions.py
=====================
Challenge 1 — Messy Transactions
Reads  : input.csv  (same folder as this script)
Writes : cleaned.csv, report.json  (same folder)

Standard-library only.  Python 3.8+.
"""

import csv
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

# -
# CONFIGURATION
# -
TREAT_AMBIGUOUS_DATES_AS_INVALID = True   # change to False to assume day/month

HERE        = Path(__file__).parent
INPUT_FILE  = HERE / "input.csv"
OUTPUT_CSV  = HERE / "cleaned.csv"
OUTPUT_JSON = HERE / "report.json"

# Columns written to cleaned.csv (in order)
OUTPUT_COLUMNS = [
    "input_row",
    "transaction_id",
    "order_id",
    "customer_name_clean",
    "amount_clean",
    "transaction_date_clean",
    "status_clean",
    # originals
    "transaction_id_original",
    "customer_name_original",
    "amount_original",
    "transaction_date_original",
    "status_original",
    # quality
    "validity",
    "issue_count",
    "issue_codes",
    "issues",
    "is_duplicate_transaction_id",
    "is_possible_duplicate",
    "duplicate_of",
]

# -
# STEP 1: LOAD RAW CSV
# -

def load_raw_rows(filepath: Path) -> list[dict]:
    """
    Read every row from the CSV and attach a 1-based input_row number.
    We use csv.DictReader so column names come from the header line.
    """
    rows = []
    with open(filepath, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader, start=1):
            row["input_row"] = i          # original 1-based row index
            rows.append(dict(row))        # make a plain dict
    return rows


# -
# STEP 2: CLEAN CUSTOMER NAMES
# -

def clean_name(raw: str) -> tuple[str, list[str], list[str]]:
    """
    Clean a customer name.

    Rules
    -----
    • Trim leading/trailing whitespace; collapse internal runs of spaces.
    • "Last, First"  →  "First Last"   (quoted CSV form or plain "Smith, John")
    • Title-case every word.
    • Blank (or whitespace-only) name is INVALID.

    Returns
    -------
    (clean_name, issue_codes, issue_messages)
    The clean_name is "" when the name is invalid.
    """
    if not raw or not raw.strip():
        return "", ["INVALID_NAME"], ["Customer name is blank or missing"]

    # Collapse multiple spaces → single space, strip ends
    name = " ".join(raw.split())

    # Detect "Last, First" pattern: one comma, two non-empty parts
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and all(parts):
            name = f"{parts[1]} {parts[0]}"   # "First Last"

    name = name.title()   # Capitalise Each Word
    return name, [], []


def canonical_name(clean: str) -> str:
    """Lower-case key used to recognise the same person across rows."""
    return clean.lower()


# -
# STEP 3: CLEAN DATES
# -

def clean_date(raw: str) -> tuple[str, list[str], list[str]]:
    """
    Parse a date string and return YYYY-MM-DD, or "" if invalid.

    Strategy
    --------
    1. Strip a trailing time component (HH:MM:SS).
    2. Try month-name formats ("5 Jan 2026", "Jan 5 2026").
    3. Try year-first numeric formats (2026-09-04, 2026/09/04).
    4. Try year-last numeric formats (DD/MM/YYYY or MM/DD/YYYY).
       When both parts ≤ 12 and they differ → AMBIGUOUS:
         • TREAT_AMBIGUOUS_DATES_AS_INVALID=True  → invalid
         • TREAT_AMBIGUOUS_DATES_AS_INVALID=False → assume day/month

    Returns
    -------
    (date_str, issue_codes, issue_messages)
    """
    if not raw or not raw.strip():
        return "", ["INVALID_DATE"], ["Transaction date is blank or missing"]

    raw_stripped = raw.strip()

    # - Strip trailing time (e.g. "2026-03-15 14:30:00" or "T14:30")
    time_pattern = r"[\s T]\d{1,2}:\d{2}(:\d{2})?$"
    date_str_only = re.sub(time_pattern, "", raw_stripped).strip()

    # - Month-name formats  e.g. "5 Jan 2026"  "January 5, 2026"
    month_name_fmts = [
        "%d %b %Y", "%d %B %Y",     # 5 Jan 2026 / 5 January 2026
        "%b %d %Y", "%B %d %Y",     # Jan 5 2026
        "%b %d, %Y", "%B %d, %Y",   # Jan 5, 2026
    ]
    for fmt in month_name_fmts:
        try:
            d = datetime.strptime(date_str_only, fmt).date()
            return d.isoformat(), [], []
        except ValueError:
            pass

    # - Year-first: YYYY-MM-DD or YYYY/MM/DD
    year_first = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", date_str_only)
    if year_first:
        y, m, d = int(year_first.group(1)), int(year_first.group(2)), int(year_first.group(3))
        return _try_build_date(y, m, d, raw)

    # - Year-last: DD/MM/YYYY or MM/DD/YYYY  (separator - or /)
    year_last = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", date_str_only)
    if year_last:
        p1, p2, y = int(year_last.group(1)), int(year_last.group(2)), int(year_last.group(3))
        return _resolve_day_month(p1, p2, y, raw)

    # - Nothing matched
    return "", ["INVALID_DATE"], [f"Unrecognised date format: '{raw}'"]


def _try_build_date(year: int, month: int, day: int, raw: str) -> tuple[str, list, list]:
    """Validate calendar correctness and return ISO string or error."""
    try:
        d = date(year, month, day)
        return d.isoformat(), [], []
    except ValueError:
        return "", ["INVALID_DATE"], [f"Impossible date: '{raw}'"]


def _resolve_day_month(p1: int, p2: int, year: int, raw: str) -> tuple[str, list, list]:
    """
    Resolve year-last dates where p1 and p2 are the two small parts.

    Ambiguity rule:
    • If one part > 12, it must be the day  → unambiguous.
    • If both parts are equal  → only one reading → unambiguous.
    • If both parts ≤ 12 and they differ  → AMBIGUOUS.
    """
    if p1 > 12:
        # p1 must be day
        return _try_build_date(year, p2, p1, raw)
    if p2 > 12:
        # p2 must be day
        return _try_build_date(year, p1, p2, raw)
    if p1 == p2:
        # e.g. 09/09/2026 – same reading either way
        return _try_build_date(year, p1, p2, raw)

    # Both ≤ 12 and differ → AMBIGUOUS
    if TREAT_AMBIGUOUS_DATES_AS_INVALID:
        return "", ["AMBIGUOUS_DATE"], [
            f"Ambiguous date '{raw}': could be {year}-{p2:02d}-{p1:02d} "
            f"or {year}-{p1:02d}-{p2:02d}"
        ]
    else:
        # Assume day/month (European convention)
        return _try_build_date(year, p2, p1, raw)


# -
# STEP 4: CLEAN AMOUNTS
# -

# Patterns that look like numbers but are explicitly invalid
_SCIENTIFIC_RE   = re.compile(r"[\deE]+[eE][\d]+")     # 1e5, 1E10
_ACCOUNTING_RE   = re.compile(r"^\(.*\)$")              # (250.00)

def clean_amount(raw: str) -> tuple[str, list[str], list[str]]:
    """
    Parse an amount string to a positive Decimal (2 dp) or return "" if invalid.

    Supported formats
    -----------------
    • 1234.56          standard
    • 1,234.56         US thousands
    • 1.234,56         European (comma decimal, period thousands)
    • 1 234,56         space thousands, comma decimal
    • 12,34,567.89     Indian grouping (period decimal)
    • € 45,50          currency symbol prefix, European decimal
    • 45,50            European decimal (no thousands group)

    Invalid values
    --------------
    • Blank / whitespace-only
    • Text strings  (N/A, oops …)
    • Zero
    • Negative  (-500)
    • Accounting style  (250.00)
    • Scientific notation  (1e5)
    • Refunds recorded as negatives (requirement: use status=refund + positive amount)
    """
    if not raw or not raw.strip():
        return "", ["INVALID_AMOUNT"], ["Amount is blank or missing"]

    s = raw.strip()

    # Accounting style (brackets) → invalid
    if _ACCOUNTING_RE.match(s):
        return "", ["INVALID_AMOUNT"], [f"Accounting-style amount not accepted: '{raw}'"]

    # Scientific notation → invalid
    if _SCIENTIFIC_RE.search(s):
        return "", ["INVALID_AMOUNT"], [f"Scientific notation not accepted: '{raw}'"]

    # Strip currency symbols and letter codes at start/end
    # (USD, EUR, GBP, INR, €, $, £, ₹ …)
    s = re.sub(r"^[€$£₹\s]+", "", s)       # leading symbols
    s = re.sub(r"\s*[A-Z]{3}\s*$", "", s)  # trailing 3-letter code (USD etc.)
    s = s.strip()

    # Negative sign
    if s.startswith("-"):
        return "", ["INVALID_AMOUNT"], [f"Negative amount not accepted: '{raw}'"]

    # Detect format by counting separators
    decimal_val = _parse_numeric_string(s)
    if decimal_val is None:
        return "", ["INVALID_AMOUNT"], [f"Cannot parse amount: '{raw}'"]

    # Zero is invalid
    if decimal_val == 0:
        return "", ["INVALID_AMOUNT"], ["Amount is zero"]

    # Round to 2 decimal places
    try:
        result = decimal_val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return "", ["INVALID_AMOUNT"], [f"Cannot quantize amount: '{raw}'"]

    return str(result), [], []


def _parse_numeric_string(s: str) -> Optional[Decimal]:
    """
    Convert a cleaned string (no currency symbol, no sign) to Decimal.

    Detection logic
    ---------------
    • If it contains both '.' and ','  → identify which is thousands and which is decimal
      - last separator is '.'  → US / Indian style  (1,234.56  or  12,34,567.89)
      - last separator is ','  → European style      (1.234,56  or  € 45,50 after strip)
    • If it contains only ','
      - comma is the decimal separator (European short form) if it appears
        exactly once and there are at most 2 digits after it — e.g. 45,50
      - otherwise comma is a thousands separator
    • If it contains only '.'  → standard decimal point  1234.56
    • Spaces as thousands separators are removed first  (1 234,56 → 1234,56)
    """
    # Remove space-as-thousands-separator
    s = s.replace(" ", "")

    dot_pos   = s.rfind(".")
    comma_pos = s.rfind(",")

    if dot_pos == -1 and comma_pos == -1:
        # Plain integer
        try:
            return Decimal(s)
        except InvalidOperation:
            return None

    if dot_pos != -1 and comma_pos != -1:
        # Both separators present
        if dot_pos > comma_pos:
            # Period is the decimal separator  (1,234.56 or 12,34,567.89)
            cleaned = s.replace(",", "")     # drop thousands commas
        else:
            # Comma is the decimal separator  (1.234,56)
            cleaned = s.replace(".", "").replace(",", ".")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    if comma_pos != -1:
        # Only commas — decide if decimal or thousands
        after_last_comma = s[comma_pos + 1:]
        if len(after_last_comma) <= 2 and s.count(",") == 1:
            # European decimal e.g. 45,50  or  1234,56
            cleaned = s.replace(",", ".")
        else:
            # Thousands comma  e.g.  1,234  (no cents shown)
            cleaned = s.replace(",", "")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    # Only dots — standard
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


# -
# STEP 5: CLEAN STATUS
# -

# Mapping from raw (lower-cased) values to canonical values
STATUS_MAP = {
    "paid"      : "paid",
    "pending"   : "pending",
    "cancelled" : "cancelled",
    "canceled"  : "cancelled",   # US spelling → canonical
    "refunded"  : "refund",      # past tense → canonical
    "refund"    : "refund",
}

def clean_status(raw: str) -> tuple[str, list[str], list[str]]:
    """
    Map raw status to one of: paid, pending, cancelled, refund.
    Anything not in the map → "unknown" and INVALID_STATUS.
    """
    if not raw or not raw.strip():
        return "unknown", ["INVALID_STATUS"], ["Status is blank or missing"]

    key = raw.strip().lower()
    canonical = STATUS_MAP.get(key)
    if canonical:
        return canonical, [], []

    return "unknown", ["INVALID_STATUS"], [f"Unrecognised status: '{raw}'"]


# -
# STEP 6: BUILD A SINGLE CLEANED ROW
# -

def clean_row(raw: dict) -> dict:
    """
    Accept one raw CSV row (as a dict) and return a cleaned row dict.

    The cleaned dict contains every OUTPUT_COLUMNS key plus helpers
    used by the duplicate-detection pass (name_key, parsed_date).
    """
    # - Extract raw fields
    tid        = (raw.get("transaction_id") or "").strip()
    oid        = (raw.get("order_id")       or "").strip()
    name_raw   = raw.get("customer_name", "") or ""
    amount_raw = raw.get("amount", "")       or ""
    date_raw   = raw.get("transaction_date", "") or ""
    status_raw = raw.get("status", "")       or ""
    row_num    = raw["input_row"]

    # - Clean each field
    name_clean,   name_codes,   name_msgs   = clean_name(name_raw)
    amount_clean, amount_codes, amount_msgs = clean_amount(amount_raw)
    date_clean,   date_codes,   date_msgs   = clean_date(date_raw)
    status_clean, status_codes, status_msgs = clean_status(status_raw)

    # - Collect all issue codes and messages
    all_codes = name_codes + amount_codes + date_codes + status_codes
    all_msgs  = name_msgs  + amount_msgs  + date_msgs  + status_msgs

    # - Determine overall validity
    valid = len(all_codes) == 0

    return {
        # - Core cleaned fields
        "input_row"               : row_num,
        "transaction_id"          : tid,
        "order_id"                : oid,
        "customer_name_clean"     : name_clean,
        "amount_clean"            : amount_clean,
        "transaction_date_clean"  : date_clean,
        "status_clean"            : status_clean,
        # - Originals (preserved verbatim)
        "transaction_id_original" : tid,
        "customer_name_original"  : name_raw,
        "amount_original"         : amount_raw,
        "transaction_date_original": date_raw,
        "status_original"         : status_raw,
        # - Quality fields (duplicates added later)
        "validity"                : "valid" if valid else "invalid",
        "issue_count"             : len(all_codes),
        "issue_codes"             : "|".join(all_codes),
        "issues"                  : "; ".join(all_msgs),
        "is_duplicate_transaction_id": False,
        "is_possible_duplicate"      : False,
        "duplicate_of"               : "",
        # - Internal helpers (not written to CSV)
        "_name_key"               : canonical_name(name_clean) if name_clean else "",
        "_amount_decimal"         : Decimal(amount_clean) if amount_clean else None,
        "_valid"                  : valid,
    }


# -
# STEP 7: DUPLICATE DETECTION
# -

def _date_can_match(date_a: str, date_b: str, raw_date_a: str, raw_date_b: str) -> bool:
    """
    Return True if date_a and date_b can be considered the same date.

    For non-ambiguous dates a simple equality check suffices.
    For a row that has AMBIGUOUS_DATE (date_clean is ""), we try both
    possible interpretations and see if either matches the other row's date.
    """
    if date_a and date_b:
        return date_a == date_b   # both resolved → simple equality

    # One or both dates are blank.  Check if the raw ambiguous form could match.
    for raw_date in (raw_date_a, raw_date_b):
        other_date = date_b if raw_date == raw_date_a else date_a
        if not other_date:
            continue   # can't compare two blanks
        both_readings = _ambiguous_readings(raw_date)
        if other_date in both_readings:
            return True
    return False


def _ambiguous_readings(raw: str) -> list[str]:
    """
    For a year-last date string, return the set of ISO strings it could mean.
    Returns an empty list if the string is not a year-last numeric date.
    """
    s = raw.strip()
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", s)
    if not m:
        return []
    p1, p2, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    results = []
    for day, month in [(p1, p2), (p2, p1)]:
        try:
            results.append(date(y, month, day).isoformat())
        except ValueError:
            pass
    return list(set(results))


def detect_duplicates(rows: list[dict]) -> list[dict]:
    """
    Two-pass duplicate detection.

    Pass 1 – Duplicate transaction ID
    -----------------------------------
    Group by transaction_id.  Keep the FIRST occurrence; flag all later
    rows with DUPLICATE_ID and record whether details match or conflict.

    Pass 2 – Possible duplicate
    ----------------------------
    Among rows NOT already flagged as duplicate IDs (and not already
    consumed as the kept row for a possible-dup group), find rows that share
    the same (name_key, amount_decimal, status_clean, order_id) AND whose
    dates can match.  Keep the earliest; flag the rest.

    Exception: rows whose only status difference is paid vs refund are NOT
    possible duplicates (a refund is a valid separate transaction).
    """

    # - Pass 1: duplicate transaction IDs -
    seen_ids: dict[str, int] = {}   # tid → index of first occurrence

    for idx, row in enumerate(rows):
        tid = row["transaction_id"]
        if not tid:
            continue   # blank ID — skip dup-ID logic

        if tid not in seen_ids:
            seen_ids[tid] = idx
        else:
            kept_idx  = seen_ids[tid]
            kept_row  = rows[kept_idx]

            # Do the key details match?
            match = (
                row["customer_name_clean"]    == kept_row["customer_name_clean"]
                and row["amount_clean"]        == kept_row["amount_clean"]
                and row["transaction_date_clean"] == kept_row["transaction_date_clean"]
                and row["status_clean"]        == kept_row["status_clean"]
            )
            detail = "details match" if match else "details conflict"

            _add_issue(row, "DUPLICATE_ID",
                       f"Duplicate transaction ID {tid} (row kept: {kept_row['input_row']}, {detail})")
            row["is_duplicate_transaction_id"] = True
            row["duplicate_of"]                = kept_row["transaction_id"]

    # - Pass 2: possible duplicates -
    # We compare only rows that are still considered valid or at worst only
    # flagged for OTHER reasons (not already a DUPLICATE_ID row).
    # Two rows are possible dups if name + amount + status + order_id match
    # AND dates can match.
    # "paid" vs "refund" on the same order is NOT a duplicate.

    # We'll use a list of (row_index, key_tuple) for comparison.
    # Key: (name_key, amount_decimal, order_id)  — status handled separately.
    # We do an O(n²) scan; n is small in practice.

    for i in range(len(rows)):
        if rows[i]["is_duplicate_transaction_id"]:
            continue   # already flagged — skip

        for j in range(i + 1, len(rows)):
            if rows[j]["is_duplicate_transaction_id"]:
                continue

            ri, rj = rows[i], rows[j]

            # Same status, name, amount, order_id?
            if (ri["status_clean"]    != rj["status_clean"]
                    or ri["_name_key"]    != rj["_name_key"]
                    or ri["_name_key"]    == ""                # blank name — skip
                    or ri["_amount_decimal"] is None
                    or rj["_amount_decimal"] is None
                    or ri["_amount_decimal"] != rj["_amount_decimal"]
                    or ri["order_id"]      != rj["order_id"]):
                continue

            # Dates must be able to match
            if not _date_can_match(
                ri["transaction_date_clean"], rj["transaction_date_clean"],
                ri["transaction_date_original"], rj["transaction_date_original"]
            ):
                continue

            # It's a possible duplicate — flag the LATER row (j)
            if not rows[j]["is_possible_duplicate"]:
                _add_issue(rows[j], "POSSIBLE_DUPLICATE",
                           f"Possible duplicate of row {ri['input_row']} "
                           f"(same customer, amount, status, order_id, matching date)")
                rows[j]["is_possible_duplicate"] = True
                rows[j]["duplicate_of"] = rows[i]["transaction_id"]

    return rows


def _add_issue(row: dict, code: str, message: str):
    """Append an issue code and message to a row and mark it invalid."""
    existing_codes = row["issue_codes"].split("|") if row["issue_codes"] else []
    existing_msgs  = row["issues"].split("; ")     if row["issues"]      else []

    existing_codes.append(code)
    existing_msgs.append(message)

    row["issue_codes"]  = "|".join(c for c in existing_codes if c)
    row["issues"]       = "; ".join(m for m in existing_msgs  if m)
    row["issue_count"]  = len([c for c in row["issue_codes"].split("|") if c])
    row["validity"]     = "invalid"
    row["_valid"]       = False


# -
# STEP 8: REVENUE CALCULATION
# -

def compute_revenue(rows: list[dict]) -> dict:
    """
    Revenue counts only VALID rows.
    total_revenue = sum(paid amounts) − sum(refund amounts)
    Pending and cancelled rows are excluded from revenue.
    """
    paid_total   = Decimal("0.00")
    refund_total = Decimal("0.00")
    paid_count   = 0
    refund_count = 0

    for row in rows:
        if not row["_valid"]:
            continue
        amt    = row["_amount_decimal"]
        status = row["status_clean"]

        if status == "paid" and amt is not None:
            paid_total  += amt
            paid_count  += 1
        elif status == "refund" and amt is not None:
            refund_total += amt
            refund_count += 1

    total = paid_total - refund_total
    return {
        "paid_total"         : str(paid_total.quantize(Decimal("0.01"))),
        "refund_total"       : str(refund_total.quantize(Decimal("0.01"))),
        "paid_rows_counted"  : paid_count,
        "refund_rows_counted": refund_count,
        "total_revenue"      : str(total.quantize(Decimal("0.01"))),
    }


# -
# STEP 9: WRITE cleaned.csv
# -

def write_cleaned_csv(rows: list[dict], filepath: Path):
    """Write the cleaned rows to a UTF-8 CSV file (no BOM)."""
    with open(filepath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            # Booleans → plain strings for readability
            out = dict(row)
            out["is_duplicate_transaction_id"] = str(row["is_duplicate_transaction_id"])
            out["is_possible_duplicate"]        = str(row["is_possible_duplicate"])
            writer.writerow(out)


# -
# STEP 10: WRITE report.json
# -

def write_report(rows: list[dict], revenue: dict, filepath: Path):
    """
    Build and write the JSON report.

    Keys
    ----
    input_rows, valid_rows, invalid_rows,
    duplicate_transaction_ids  (count of distinct IDs that appear >1 time),
    duplicate_transaction_id_rows  (count of flagged repeated rows),
    possible_duplicate_rows,
    total_revenue,
    revenue_breakdown,
    rows_by_issue_code
    """
    # - Count rows
    input_rows   = len(rows)
    valid_rows   = sum(1 for r in rows if r["_valid"])
    invalid_rows = input_rows - valid_rows

    # - Duplicate transaction IDs
    id_counts: dict[str, int] = {}
    for r in rows:
        tid = r["transaction_id"]
        if tid:
            id_counts[tid] = id_counts.get(tid, 0) + 1
    dup_id_distinct = sum(1 for cnt in id_counts.values() if cnt > 1)
    dup_id_rows     = sum(1 for r in rows if r["is_duplicate_transaction_id"])

    # - Possible duplicates
    possible_dup_rows = sum(1 for r in rows if r["is_possible_duplicate"])

    # - Rows by issue code
    code_counts: dict[str, int] = {}
    for r in rows:
        for code in r["issue_codes"].split("|"):
            if code:
                code_counts[code] = code_counts.get(code, 0) + 1

    report = {
        "input_rows"                   : input_rows,
        "valid_rows"                   : valid_rows,
        "invalid_rows"                 : invalid_rows,
        "duplicate_transaction_ids"    : dup_id_distinct,
        "duplicate_transaction_id_rows": dup_id_rows,
        "possible_duplicate_rows"      : possible_dup_rows,
        "total_revenue"                : revenue["total_revenue"],
        "revenue_breakdown"            : {
            "paid_total"          : revenue["paid_total"],
            "refund_total"        : revenue["refund_total"],
            "paid_rows_counted"   : revenue["paid_rows_counted"],
            "refund_rows_counted" : revenue["refund_rows_counted"],
        },
        "rows_by_issue_code"           : code_counts,
    }

    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    return report


# -
# STEP 11: SELF-CHECK
# -

def self_check(cleaned_path: Path, input_path: Path, report: dict, rows: list[dict]):
    """
    Re-read cleaned.csv and input.csv from disk and verify every claim.
    Raises AssertionError if anything does not reconcile.
    """
    print("\n- Self-check -")

    # - Re-count input rows (excluding header)
    with open(input_path, newline="", encoding="utf-8") as fh:
        raw_input_count = sum(1 for r in csv.DictReader(fh))
    assert raw_input_count == report["input_rows"], (
        f"Input row count mismatch: file has {raw_input_count}, "
        f"report says {report['input_rows']}"
    )
    print(f"  OK input rows = {raw_input_count}")

    # - Re-read cleaned.csv
    with open(cleaned_path, newline="", encoding="utf-8") as fh:
        cleaned_rows = list(csv.DictReader(fh))

    assert len(cleaned_rows) == report["input_rows"], (
        f"cleaned.csv has {len(cleaned_rows)} rows, expected {report['input_rows']}"
    )
    print(f"  OK cleaned.csv row count = {len(cleaned_rows)}")

    # - Valid + invalid = total
    re_valid   = sum(1 for r in cleaned_rows if r["validity"] == "valid")
    re_invalid = sum(1 for r in cleaned_rows if r["validity"] == "invalid")
    assert re_valid + re_invalid == report["input_rows"], "valid+invalid ≠ input_rows"
    assert re_valid   == report["valid_rows"],   f"valid count mismatch: {re_valid} vs {report['valid_rows']}"
    assert re_invalid == report["invalid_rows"], f"invalid count mismatch"
    print(f"  OK valid={re_valid}, invalid={re_invalid}")

    # - Every invalid row has a non-empty explanation
    for r in cleaned_rows:
        if r["validity"] == "invalid":
            assert r["issues"].strip(), (
                f"Row {r['input_row']} is invalid but has no issue text"
            )

    # - Every valid row: all critical fields are non-empty
    for r in cleaned_rows:
        if r["validity"] == "valid":
            assert r["customer_name_clean"].strip(), f"Row {r['input_row']} valid but name empty"
            assert r["amount_clean"].strip(),        f"Row {r['input_row']} valid but amount empty"
            assert r["transaction_date_clean"].strip(), f"Row {r['input_row']} valid but date empty"
            assert r["status_clean"] in ("paid","pending","cancelled","refund"), \
                f"Row {r['input_row']} valid but status unknown"
    print("  OK every valid row has clean name, amount, date, status")

    # - Duplicate ID count
    re_dup_id_rows = sum(1 for r in cleaned_rows if r["is_duplicate_transaction_id"] == "True")
    assert re_dup_id_rows == report["duplicate_transaction_id_rows"], (
        f"dup-id row count mismatch: {re_dup_id_rows} vs {report['duplicate_transaction_id_rows']}"
    )
    print(f"  OK duplicate_transaction_id_rows = {re_dup_id_rows}")

    # - Possible duplicate count
    re_poss_dup = sum(1 for r in cleaned_rows if r["is_possible_duplicate"] == "True")
    assert re_poss_dup == report["possible_duplicate_rows"], (
        f"possible_dup count mismatch: {re_poss_dup} vs {report['possible_duplicate_rows']}"
    )
    print(f"  OK possible_duplicate_rows = {re_poss_dup}")

    # - Revenue recompute
    paid_r   = Decimal("0.00")
    refund_r = Decimal("0.00")
    for r in cleaned_rows:
        if r["validity"] == "valid" and r["amount_clean"]:
            amt = Decimal(r["amount_clean"])
            if r["status_clean"] == "paid":
                paid_r += amt
            elif r["status_clean"] == "refund":
                refund_r += amt

    total_r = paid_r - refund_r
    assert str(total_r.quantize(Decimal("0.01"))) == report["total_revenue"], (
        f"Revenue mismatch: recomputed {total_r}, report says {report['total_revenue']}"
    )
    print(f"  OK total_revenue = {total_r}")
    print("-- Self-check PASSED -----------------------------------\n")


# -
# STEP 12: MAIN PIPELINE
# -

def main():
    """Entry point: orchestrate the full pipeline."""
    print(f"Reading  : {INPUT_FILE}")

    # 1. Load raw rows
    raw_rows = load_raw_rows(INPUT_FILE)
    print(f"  {len(raw_rows)} data rows found")

    # 2. Clean each row
    cleaned = [clean_row(r) for r in raw_rows]

    # 3. Detect duplicates (modifies rows in place)
    cleaned = detect_duplicates(cleaned)

    # 4. Compute revenue
    revenue = compute_revenue(cleaned)

    # 5. Write outputs
    write_cleaned_csv(cleaned, OUTPUT_CSV)
    report = write_report(cleaned, revenue, OUTPUT_JSON)

    print(f"Written  : {OUTPUT_CSV}")
    print(f"Written  : {OUTPUT_JSON}")
    print()
    print("--- Summary --------------------------------------------")
    print(f"  Input rows   : {report['input_rows']}")
    print(f"  Valid rows   : {report['valid_rows']}")
    print(f"  Invalid rows : {report['invalid_rows']}")
    print(f"  Dup-ID rows  : {report['duplicate_transaction_id_rows']}")
    print(f"  Poss-dup rows: {report['possible_duplicate_rows']}")
    print(f"  Total revenue: {report['total_revenue']}")
    print("--------------------------------------------------------")

    # 6. Self-check (reads files from disk, re-verifies everything)
    self_check(OUTPUT_CSV, INPUT_FILE, report, cleaned)

    return 0


if __name__ == "__main__":
    sys.exit(main())
