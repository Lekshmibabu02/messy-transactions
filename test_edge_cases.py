"""
test_edge_cases.py
==================
Unit tests for clean_transactions.py
Covers every edge case listed in the assignment.
Uses only the Python standard library (unittest).

Run:
    python test_edge_cases.py -v
"""

import csv
import io
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

# ── make sure we can import our module from the same folder
sys.path.insert(0, str(Path(__file__).parent))
import clean_transactions as ct


# ─────────────────────────────────────────────
# HELPER: build a minimal raw row dict
# ─────────────────────────────────────────────

def make_row(
    tid="TX1", oid="O1", name="Alice Johnson",
    amount="100.00", date="2026-01-01", status="paid",
    row=1,
):
    """Return a minimal raw-dict as load_raw_rows would produce it."""
    return {
        "transaction_id"  : tid,
        "order_id"        : oid,
        "customer_name"   : name,
        "amount"          : amount,
        "transaction_date": date,
        "status"          : status,
        "input_row"       : row,
    }


# ─────────────────────────────────────────────
# 1. NAME CLEANING
# ─────────────────────────────────────────────

class TestNameCleaning(unittest.TestCase):

    def test_basic_title_case(self):
        name, codes, _ = ct.clean_name("alice johnson")
        self.assertEqual(name, "Alice Johnson")
        self.assertEqual(codes, [])

    def test_trim_and_collapse_spaces(self):
        name, codes, _ = ct.clean_name("  bob   williams  ")
        self.assertEqual(name, "Bob Williams")
        self.assertEqual(codes, [])

    def test_last_first_inversion(self):
        name, codes, _ = ct.clean_name("Smith, John")
        self.assertEqual(name, "John Smith")
        self.assertEqual(codes, [])

    def test_already_upper(self):
        name, codes, _ = ct.clean_name("ALICE JOHNSON")
        self.assertEqual(name, "Alice Johnson")
        self.assertEqual(codes, [])

    def test_blank_name(self):
        name, codes, msgs = ct.clean_name("")
        self.assertEqual(name, "")
        self.assertIn("INVALID_NAME", codes)

    def test_whitespace_only(self):
        name, codes, msgs = ct.clean_name("   ")
        self.assertEqual(name, "")
        self.assertIn("INVALID_NAME", codes)

    def test_canonical_key(self):
        """Same person, different raw formats → same canonical key."""
        n1, _, _ = ct.clean_name("ALICE JOHNSON")
        n2, _, _ = ct.clean_name("  alice   johnson  ")
        self.assertEqual(ct.canonical_name(n1), ct.canonical_name(n2))


# ─────────────────────────────────────────────
# 2. DATE PARSING
# ─────────────────────────────────────────────

class TestDateParsing(unittest.TestCase):

    def test_year_first_dash(self):
        d, codes, _ = ct.clean_date("2026-01-15")
        self.assertEqual(d, "2026-01-15")
        self.assertEqual(codes, [])

    def test_year_first_slash(self):
        d, codes, _ = ct.clean_date("2026/03/20")
        self.assertEqual(d, "2026-03-20")
        self.assertEqual(codes, [])

    def test_month_name(self):
        d, codes, _ = ct.clean_date("5 Jan 2026")
        self.assertEqual(d, "2026-01-05")
        self.assertEqual(codes, [])

    def test_trailing_time(self):
        d, codes, _ = ct.clean_date("2026-03-15 14:30:00")
        self.assertEqual(d, "2026-03-15")
        self.assertEqual(codes, [])

    def test_impossible_date(self):
        d, codes, _ = ct.clean_date("2026-15-08")
        self.assertEqual(d, "")
        self.assertIn("INVALID_DATE", codes)

    def test_impossible_feb(self):
        d, codes, _ = ct.clean_date("31/02/2026")
        self.assertEqual(d, "")
        self.assertIn("INVALID_DATE", codes)

    def test_unrecognised_text(self):
        d, codes, _ = ct.clean_date("not-a-date")
        self.assertEqual(d, "")
        self.assertIn("INVALID_DATE", codes)

    def test_blank_date(self):
        d, codes, _ = ct.clean_date("")
        self.assertEqual(d, "")
        self.assertIn("INVALID_DATE", codes)

    # ── Ambiguity tests (default: TREAT_AMBIGUOUS_DATES_AS_INVALID = True)

    def test_ambiguous_date_is_invalid(self):
        """05-09-2026: could be May-9 or Sep-5 → invalid when flag is True."""
        d, codes, msgs = ct.clean_date("05-09-2026")
        self.assertEqual(d, "")
        self.assertIn("AMBIGUOUS_DATE", codes)

    def test_ambiguous_date_assume_day_month(self):
        """With flag off, 05-09-2026 → 2026-09-05 (day/month)."""
        with patch.object(ct, "TREAT_AMBIGUOUS_DATES_AS_INVALID", False):
            d, codes, _ = ct.clean_date("05-09-2026")
        self.assertEqual(d, "2026-09-05")
        self.assertEqual(codes, [])

    def test_unambiguous_high_day(self):
        """15/09/2026: 15 > 12 → must be the day → 2026-09-15."""
        d, codes, _ = ct.clean_date("15/09/2026")
        self.assertEqual(d, "2026-09-15")
        self.assertEqual(codes, [])

    def test_unambiguous_equal_parts(self):
        """09/09/2026: both parts equal → one reading → 2026-09-09."""
        d, codes, _ = ct.clean_date("09/09/2026")
        self.assertEqual(d, "2026-09-09")
        self.assertEqual(codes, [])


# ─────────────────────────────────────────────
# 3. AMOUNT PARSING
# ─────────────────────────────────────────────

class TestAmountParsing(unittest.TestCase):

    def test_standard(self):
        a, codes, _ = ct.clean_amount("1234.56")
        self.assertEqual(a, "1234.56")
        self.assertEqual(codes, [])

    def test_us_thousands(self):
        a, codes, _ = ct.clean_amount("1,234.56")
        self.assertEqual(a, "1234.56")
        self.assertEqual(codes, [])

    def test_european(self):
        """1.234,56  →  1234.56"""
        a, codes, _ = ct.clean_amount("1.234,56")
        self.assertEqual(a, "1234.56")
        self.assertEqual(codes, [])

    def test_european_symbol(self):
        """€ 45,50  →  45.50"""
        a, codes, _ = ct.clean_amount("€ 45,50")
        self.assertEqual(a, "45.50")
        self.assertEqual(codes, [])

    def test_space_thousands(self):
        """1 234,56  →  1234.56"""
        a, codes, _ = ct.clean_amount("1 234,56")
        self.assertEqual(a, "1234.56")
        self.assertEqual(codes, [])

    def test_indian(self):
        """12,34,567.89  →  1234567.89"""
        a, codes, _ = ct.clean_amount("12,34,567.89")
        self.assertEqual(a, "1234567.89")
        self.assertEqual(codes, [])

    def test_blank(self):
        a, codes, _ = ct.clean_amount("")
        self.assertEqual(a, "")
        self.assertIn("INVALID_AMOUNT", codes)

    def test_whitespace_only(self):
        a, codes, _ = ct.clean_amount("   ")
        self.assertEqual(a, "")
        self.assertIn("INVALID_AMOUNT", codes)

    def test_text_value(self):
        a, codes, _ = ct.clean_amount("N/A")
        self.assertEqual(a, "")
        self.assertIn("INVALID_AMOUNT", codes)

    def test_zero(self):
        a, codes, _ = ct.clean_amount("0")
        self.assertEqual(a, "")
        self.assertIn("INVALID_AMOUNT", codes)

    def test_negative(self):
        a, codes, _ = ct.clean_amount("-500.00")
        self.assertEqual(a, "")
        self.assertIn("INVALID_AMOUNT", codes)

    def test_accounting_style(self):
        a, codes, _ = ct.clean_amount("(250.00)")
        self.assertEqual(a, "")
        self.assertIn("INVALID_AMOUNT", codes)

    def test_scientific(self):
        a, codes, _ = ct.clean_amount("1e5")
        self.assertEqual(a, "")
        self.assertIn("INVALID_AMOUNT", codes)


# ─────────────────────────────────────────────
# 4. STATUS MAPPING
# ─────────────────────────────────────────────

class TestStatusMapping(unittest.TestCase):

    def test_paid(self):
        s, codes, _ = ct.clean_status("paid")
        self.assertEqual(s, "paid")
        self.assertEqual(codes, [])

    def test_pending(self):
        s, codes, _ = ct.clean_status("pending")
        self.assertEqual(s, "pending")

    def test_cancelled_uk(self):
        s, codes, _ = ct.clean_status("cancelled")
        self.assertEqual(s, "cancelled")

    def test_canceled_us(self):
        """US spelling 'canceled' → canonical 'cancelled'."""
        s, codes, _ = ct.clean_status("canceled")
        self.assertEqual(s, "cancelled")

    def test_refunded(self):
        """'refunded' → canonical 'refund'."""
        s, codes, _ = ct.clean_status("refunded")
        self.assertEqual(s, "refund")

    def test_refund(self):
        s, codes, _ = ct.clean_status("refund")
        self.assertEqual(s, "refund")

    def test_unknown(self):
        s, codes, _ = ct.clean_status("unknown_status")
        self.assertEqual(s, "unknown")
        self.assertIn("INVALID_STATUS", codes)

    def test_blank_status(self):
        s, codes, _ = ct.clean_status("")
        self.assertEqual(s, "unknown")
        self.assertIn("INVALID_STATUS", codes)


# ─────────────────────────────────────────────
# 5. IN-MEMORY DUPLICATE DETECTION
# ─────────────────────────────────────────────

class TestDuplicateDetection(unittest.TestCase):
    """
    Scenario described in the assignment:
    Alice Johnson / O101 / 1200.00 entered three ways:
      Row A: status=paid,   date=2026-09-03 (clean, unambiguous)
      Row B: status=refund, date=2026-09-03  ← NOT a duplicate of A
      Row C: status=paid,   date=03/09/2026  ← ambiguous, can match A → possible dup
      Row D: status=paid,   "  alice   johnson  " + "1200.00 " extra spaces → same cleaned key → possible dup of A
    """

    def _build_and_detect(self, rows_raw):
        cleaned = [ct.clean_row(r) for r in rows_raw]
        return ct.detect_duplicates(cleaned)

    def test_exact_duplicate_id(self):
        """Same transaction_id twice → second row flagged as DUPLICATE_ID."""
        rows = [
            make_row(tid="TID1", row=1),
            make_row(tid="TID1", row=2),
        ]
        result = self._build_and_detect(rows)
        self.assertFalse(result[0]["is_duplicate_transaction_id"])
        self.assertTrue(result[1]["is_duplicate_transaction_id"])
        self.assertIn("DUPLICATE_ID", result[1]["issue_codes"])

    def test_refund_is_not_a_possible_duplicate(self):
        """Same name/order/amount but paid vs refund → NOT flagged."""
        rows = [
            make_row(tid="A", oid="O1", name="Alice Johnson", amount="1200.00",
                     date="2026-09-03", status="paid", row=1),
            make_row(tid="B", oid="O1", name="Alice Johnson", amount="1200.00",
                     date="2026-09-03", status="refund", row=2),
        ]
        result = self._build_and_detect(rows)
        self.assertFalse(result[0]["is_possible_duplicate"])
        self.assertFalse(result[1]["is_possible_duplicate"])

    def test_ambiguous_date_matches_clean_date(self):
        """
        Row C has ambiguous date 03/09/2026.
        If either reading (2026-09-03 or 2026-03-09) matches Row A's clean date
        (2026-09-03), Row C is a possible duplicate.
        """
        rows = [
            make_row(tid="A", oid="O1", name="Alice Johnson", amount="1200.00",
                     date="2026-09-03", status="paid", row=1),
            make_row(tid="C", oid="O1", name="Alice Johnson", amount="1200.00",
                     date="03/09/2026", status="paid", row=2),   # ambiguous
        ]
        result = self._build_and_detect(rows)
        self.assertFalse(result[0]["is_possible_duplicate"])
        self.assertTrue(result[1]["is_possible_duplicate"])
        self.assertIn("POSSIBLE_DUPLICATE", result[1]["issue_codes"])

    def test_extra_spaces_in_name_same_person(self):
        """'  alice   johnson  ' cleaned → 'Alice Johnson' → same key → possible dup."""
        rows = [
            make_row(tid="A", oid="O1", name="Alice Johnson", amount="1200.00",
                     date="2026-09-03", status="paid", row=1),
            make_row(tid="D", oid="O1", name="  alice   johnson  ", amount="1200.00",
                     date="2026-09-03", status="paid", row=2),
        ]
        result = self._build_and_detect(rows)
        self.assertFalse(result[0]["is_possible_duplicate"])
        self.assertTrue(result[1]["is_possible_duplicate"])

    def test_three_rows_scenario(self):
        """
        Full 3-row scenario:
        Row 1: paid, clean date
        Row 2: refund, same details → NOT a dup (different status category for dup logic)
        Row 3: paid, ambiguous date that can match row 1 → POSSIBLE_DUPLICATE
        """
        rows = [
            make_row(tid="A", oid="O1", name="Alice Johnson", amount="1200.00",
                     date="2026-09-03", status="paid",   row=1),
            make_row(tid="B", oid="O1", name="Alice Johnson", amount="1200.00",
                     date="2026-09-03", status="refund", row=2),
            make_row(tid="C", oid="O1", name="  alice   johnson  ", amount="1200.00",
                     date="03/09/2026", status="paid",   row=3),
        ]
        result = self._build_and_detect(rows)

        self.assertFalse(result[0]["is_possible_duplicate"], "Row 1 should be kept")
        self.assertFalse(result[1]["is_possible_duplicate"], "Refund is not a dup of paid")
        self.assertTrue(result[2]["is_possible_duplicate"],  "Row 3 is dup of row 1")


# ─────────────────────────────────────────────
# 6. REVENUE CALCULATION
# ─────────────────────────────────────────────

class TestRevenue(unittest.TestCase):

    def _make_valid_row(self, tid, status, amount_str):
        """Build a cleaned row dict as detect_duplicates output."""
        r = ct.clean_row(make_row(tid=tid, status=status, amount=amount_str))
        # Force valid for simplicity (date/name are valid in make_row defaults)
        r["_valid"] = (r["validity"] == "valid")
        return r

    def test_paid_minus_refund(self):
        rows = [
            self._make_valid_row("A", "paid",   "1000.00"),
            self._make_valid_row("B", "refund", "200.00"),
            self._make_valid_row("C", "pending","500.00"),    # excluded
            self._make_valid_row("D", "cancelled","300.00"),  # excluded
        ]
        rev = ct.compute_revenue(rows)
        self.assertEqual(rev["total_revenue"], "800.00")
        self.assertEqual(rev["paid_rows_counted"], 1)
        self.assertEqual(rev["refund_rows_counted"], 1)

    def test_invalid_rows_excluded(self):
        rows = [
            self._make_valid_row("A", "paid", "1000.00"),
        ]
        rows[0]["_valid"] = False   # force invalid
        rev = ct.compute_revenue(rows)
        self.assertEqual(rev["total_revenue"], "0.00")


# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
