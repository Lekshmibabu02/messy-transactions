# Challenge 1 — Messy Transactions

Clean a messy CSV of financial transactions using only the Python standard library.

---

## Run Command

```bash
python clean_transactions.py
```

> If `python` is not recognised in VS Code terminal on Windows, use `py clean_transactions.py`.

### Run tests

```bash
python test_edge_cases.py -v
```

---

## File List

| File | Purpose |
|------|---------|
| `input.csv` | Raw messy input (30 rows, 6 columns) |
| `clean_transactions.py` | Main cleaning script — the only file you need to run |
| `cleaned.csv` | Output: every input row cleaned and annotated |
| `report.json` | Output: summary statistics and revenue |
| `test_edge_cases.py` | 47 unit tests covering every edge case |
| `README.md` | This file |

---

## Results Table

| Metric | Value (TREAT_AMBIGUOUS=True) | Value (TREAT_AMBIGUOUS=False) |
|--------|------------------------------|-------------------------------|
| Input rows | 30 | 30 |
| Valid rows | 12 | 16 |
| Invalid rows | 18 | 14 |
| Duplicate transaction ID rows | 1 | 1 |
| Possible duplicate rows | 1 | 1 |
| Total revenue | 1,234,818.63 | 1,238,464.13 |
| Paid rows counted | 5 | 9 |
| Paid total | 1,238,487.75 | 1,242,133.25 |
| Refund rows counted | 3 | 3 |
| Refund total | 3,669.12 | 3,669.12 |

**Impact of the ambiguous-date flag:** When `TREAT_AMBIGUOUS_DATES_AS_INVALID = True` (default), 4 dates like `05-09-2026` and `03/09/2026` are rejected because both parts are ≤ 12 and differ — meaning they could be May-9 or Sep-5. Changing the flag to `False` (assume day/month, European convention) rescues those 4 rows, adding 4 valid rows, increasing paid count from 5 to 9, and raising revenue by ~3,645.

---

## Issue Code Breakdown (default run)

| Issue Code | Rows |
|------------|------|
| INVALID_AMOUNT | 7 |
| AMBIGUOUS_DATE | 4 |
| INVALID_DATE | 3 |
| INVALID_STATUS | 1 |
| INVALID_NAME | 1 |
| DUPLICATE_ID | 1 |
| POSSIBLE_DUPLICATE | 1 |

---

## Assumptions

### Names
- Trim leading/trailing whitespace; collapse internal runs of spaces.
- `"Last, First"` (single comma, two parts) → `"First Last"`.
- Title-case every word.
- Lower-cased clean name is the identity key (`alice johnson` == `ALICE JOHNSON`).
- Blank or whitespace-only name → `INVALID_NAME`.

### Dates
- Output is always `YYYY-MM-DD`.
- Year-first formats (`2026-09-04`, `2026/09/04`) → read as year-month-day.
- Year-last formats (`03/09/2026`, `05-09-2026`):
  - If one part > 12, that part must be the day → unambiguous.
  - If both parts are equal → same date either way → unambiguous.
  - If both parts ≤ 12 and differ → **AMBIGUOUS**:
    - `TREAT_AMBIGUOUS_DATES_AS_INVALID = True` (default): row is invalid.
    - `TREAT_AMBIGUOUS_DATES_AS_INVALID = False`: assume day/month (European).
- Month-name dates (`5 Jan 2026`) are always unambiguous.
- Trailing time component (`14:30:00`) is stripped and date extracted.
- Calendar-impossible dates (`2026-15-08`, `31/02/2026`) → `INVALID_DATE`.
- Unrecognised text → `INVALID_DATE`.

### Amounts
- Uses `Decimal`, not `float` — no rounding errors.
- Supported: `1234.56` · `1,234.56` (US) · `1.234,56` (European) · `1 234,56` (space+comma) · `12,34,567.89` (Indian) · `€ 45,50` (symbol+European).
- Currency symbols and 3-letter codes are stripped.
- Invalid: blank, text (`N/A`), zero, negative, accounting style `(250.00)`, scientific notation `1e5`.
- Refunds must use `status=refund` with a **positive** amount.

### Statuses
- Canonical set: `paid`, `pending`, `cancelled`, `refund`.
- `canceled` → `cancelled` (US spelling accepted).
- `refunded` → `refund` (past tense accepted).
- Anything else or blank → `unknown` + `INVALID_STATUS`.

### Duplicates
- **Duplicate transaction ID**: same `transaction_id` in two rows → keep the first, flag all later ones. Record whether details match or conflict.
- **Possible duplicate**: same `customer_name_clean` + `amount_clean` + `status_clean` + `order_id` + matching date → keep earliest, flag later ones. An ambiguous date matches if *either* of its two readings equals the other row's date.
- **Exception**: `paid` vs `refund` on the same order is not a duplicate — a refund is a legitimate separate transaction.

### Revenue
- Only **valid** rows count.
- `total_revenue = sum(paid) − sum(refund)`.
- `pending` and `cancelled` rows are excluded entirely.

---

## Edge Case Demonstrated

**Scenario: same customer/order entered three ways**

| Row | TID | Name | Amount | Date | Status | Result |
|-----|-----|------|--------|------|--------|--------|
| T024 | O101 | Alice Johnson | 1234.56 | 2026-01-15 | refund | **Valid — refund is NOT a dup of paid** |
| T001 | O101 | Alice Johnson | 1234.56 | 2026-01-15 | paid | **Valid — kept as first occurrence** |
| T020 | O101 | Alice Johnson | 1234.56 | 2026-01-15 | paid | **Invalid — POSSIBLE_DUPLICATE of T001** |

**Why the refund is not a duplicate:** The possible-duplicate check requires `status_clean` to match. `refund ≠ paid`, so T024 passes through cleanly as a valid refund transaction. T020 has the same name, amount, order_id, date, AND status (`paid`) as T001, so it is flagged.

**The ambiguous-date variant:** Input rows T019 and T029 have `03/09/2026` (ambiguous) with the same name/amount/order as another row. Under the default flag, those rows are already invalid (AMBIGUOUS_DATE) before possible-duplicate logic runs, so the possible-duplicate flag is separate. Under `TREAT_AMBIGUOUS_DATES_AS_INVALID=False`, those rows resolve to `2026-09-03` and the possible-duplicate check fires, correctly flagging the later occurrence.

---

## Step-by-Step Run Instructions (VS Code on Windows)

1. **Install Python 3.12** from [python.org](https://www.python.org/downloads/).
   - On the first installer screen, tick **"Add Python to PATH"** before clicking Install.
2. **Open the project folder** in VS Code: `File → Open Folder → select the project folder`.
3. **Open the terminal**: `` Ctrl+` `` or `Terminal → New Terminal`.
4. **Run the script**:
   ```
   python clean_transactions.py
   ```
   If you see `python was not found`, use:
   ```
   py clean_transactions.py
   ```
5. **Run the tests**:
   ```
   python test_edge_cases.py -v
   ```
6. `cleaned.csv` and `report.json` will appear in the same folder.
