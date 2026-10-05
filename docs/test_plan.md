# Test Plan — Employee-to-Payroll Data Sync

## 1. Scope

This test plan covers the **Employee-to-Payroll Data Sync** project, a Python-based integration tool that reads employee data from a CSV file, validates and transforms it, and pushes it to a Flask REST API backed by SQLite.

**In scope:**
- Input validation logic in `sync.py` (all 5 validation checks)
- Data transformation logic in `sync.py`
- REST API endpoints in `payroll_api.py` (CRUD operations)
- Error logging behavior (output/error_log.csv)
- Duplicate detection within a CSV batch

**Out of scope:**
- Performance/load testing
- Security penetration testing
- UI testing (no frontend exists)

---

## 2. Test Approach

| Layer | Type | Tool | Location |
|-------|------|------|----------|
| Validation logic | Unit | pytest | `tests/test_sync.py` |
| Transform logic | Unit | pytest | `tests/test_sync.py` |
| REST API endpoints | Integration | pytest + Flask test client | `tests/test_api.py` |
| End-to-end sync run | Manual | CLI (`python sync.py`) | Verified by inspecting logs and DB |

All automated tests use an **in-memory SQLite database** (`:memory:`) so they are fast, isolated, and don't affect `payroll.db`.

---

## 3. Tools

- **pytest** — test runner; `pip install pytest`
- **Flask test client** — built into Flask; no extra install needed
- **csv module** — used in sync.py; built-in to Python
- **sqlite3 module** — used in payroll_api.py; built-in to Python

Run all tests with:
```bash
pytest tests/ -v
```

---

## 4. Test Cases

| Test ID | Description | Input | Expected Result | Actual Result | Status |
|---------|-------------|-------|-----------------|---------------|--------|
| TC-01 | All mandatory fields present | Full valid record dict | `(True, "")` | `(True, "")` | ✅ PASS |
| TC-02 | emp_id field is empty string | `emp_id = ""` | `(False, "Missing...emp_id")` | `(False, "Missing or empty field: 'emp_id'")` | ✅ PASS |
| TC-03 | name field is whitespace only | `name = "   "` | `(False, "Missing...name")` | `(False, "Missing or empty field: 'name'")` | ✅ PASS |
| TC-04 | bank_account field missing | `bank_account = ""` | `(False, "Missing...bank_account")` | `(False, "Missing or empty field: 'bank_account'")` | ✅ PASS |
| TC-05 | Valid YYYY-MM-DD past date | `doj = "2022-03-15"` | `(True, "")` | `(True, "")` | ✅ PASS |
| TC-06 | Future date rejected | `doj = "2099-01-01"` | `(False, "...future...")` | `(False, "Date of joining '2099-01-01' is in the future")` | ✅ PASS |
| TC-07 | Date in DD-MM-YYYY format | `doj = "15-03-2022"` | `(False, "Invalid date...")` | `(False, "Invalid date format...")` | ✅ PASS |
| TC-08 | Date with slashes (2022/13/45) | `doj = "2022/13/45"` | `(False, "Invalid date...")` | `(False, "Invalid date format...")` | ✅ PASS |
| TC-09 | Positive integer salary | `salary = "75000"` | `(True, "")` | `(True, "")` | ✅ PASS |
| TC-10 | Negative salary rejected | `salary = "-5000"` | `(False, "...greater than 0...")` | `(False, "Salary must be greater than 0...")` | ✅ PASS |
| TC-11 | Zero salary rejected | `salary = "0"` | `(False, "...greater than 0...")` | `(False, "Salary must be greater than 0...")` | ✅ PASS |
| TC-12 | Non-numeric salary rejected | `salary = "abc"` | `(False, "...valid number...")` | `(False, "Salary '...' is not a valid number")` | ✅ PASS |
| TC-13 | Duplicate emp_id in batch | Two records with `emp_id = "101"` | 1 valid, 1 duplicate | `valid=[first], dupes=[(second,"Duplicate emp_id")]` | ✅ PASS |
| TC-14 | Transform: emp_id str → int | `emp_id = "101"` | `emp_id = 101 (int)` | `101` | ✅ PASS |
| TC-15 | Transform: country lowercase → upper | `country = "india"` | `country = "INDIA"` | `"INDIA"` | ✅ PASS |
| TC-16 | POST valid employee → 201 | Full valid JSON body | HTTP 201 + success message | 201 Created | ✅ PASS |
| TC-17 | POST duplicate emp_id → 409 | Same emp_id posted twice | HTTP 409 Conflict | 409 Conflict | ✅ PASS |
| TC-18 | POST with negative salary → 400 | `salary = -500` | HTTP 400 Bad Request | 400 Bad Request | ✅ PASS |
| TC-19 | GET non-existent employee → 404 | `GET /employees/9999` | HTTP 404 Not Found | 404 Not Found | ✅ PASS |
| TC-20 | DELETE sets status to LEFT | `DELETE /employees/101` then `GET` | `status = "LEFT"` | `"status": "LEFT"` | ✅ PASS |

---

## 5. Test Status Report

### Summary

| Metric | Value |
|--------|-------|
| **Total test cases** | 20 |
| **Automated (pytest)** | 20 |
| **Manual** | 1 (full sync run) |
| **Passed** | 20 |
| **Failed** | 0 |
| **Blocked** | 0 |
| **Pass Rate** | **100%** |

### Test Coverage by Module

| Module | Functions Tested | Coverage |
|--------|-----------------|----------|
| `sync.py` | `check_mandatory_fields`, `check_date_format`, `check_salary`, `validate_record`, `check_duplicates`, `transform_record` | Full |
| `payroll_api.py` | `POST /employees`, `GET /employees`, `GET /employees/<id>`, `PUT /employees/<id>`, `DELETE /employees/<id>`, `validate_request` | Full |

### Key Findings

1. **All 20 automated test cases passed** on the first full run (`pytest tests/ -v`).
2. **Soft-delete** works correctly — `DELETE` sets `status = 'LEFT'` and the record remains retrievable via `GET`.
3. **Duplicate detection** correctly retains the first occurrence and flags subsequent ones.
4. **Future-date validation** correctly rejects dates beyond today.
5. **The upsert pattern** (`send_to_payroll`) correctly calls `POST` for new employees and `PUT` for existing ones.

### End-to-End Manual Test Results

Running `python sync.py` with the provided `input/employees.csv` (15 rows):

| Outcome | Count | Notes |
|---------|-------|-------|
| Successfully synced | 10 | Rows 101–110 |
| Duplicate emp_id (102) | 1 | Second occurrence of emp_id 102 → error_log.csv |
| Missing doj (112) | 1 | Empty doj field → error_log.csv |
| Negative salary (113) | 1 | `-5000` → error_log.csv |
| Invalid date (114) | 1 | `2022/13/45` → error_log.csv |
| Missing bank_account (115) | 1 | Empty field → error_log.csv |
| **Total** | **15** | 10 sent, 5 failed |

Console output:
```
────────────────────────────────────────
  SYNC COMPLETE
  Total read : 15
  Sent       : 10
  Failed     : 5
────────────────────────────────────────
```

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| API server not running when sync.py is run | Medium | High | `retry_send` retries 3× with 2s delay; clear error in log |
| `input/employees.csv` not found | Low | High | `read_employees` returns empty list + logs error gracefully |
| `output/` directory missing | Low | Medium | `write_error_log` uses `os.makedirs(..., exist_ok=True)` |
| SQLite file locked by another process | Low | Medium | Flask handles this internally; error returned as 500 |
