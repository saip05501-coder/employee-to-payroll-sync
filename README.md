# Employee-to-Payroll Data Sync

> **A beginner-friendly HR-to-Payroll integration project** — built for freshers
> preparing for Associate Integration Developer roles.

---

## What is this project?

This project simulates a **real-world data integration scenario**:

- An **HR System** stores employee records in a CSV file (`input/employees.csv`).
- A **Payroll System** exposes a REST API (`payroll_api.py`) backed by SQLite.
- A **Sync Script** (`sync.py`) acts as the integration middleware — it reads from the HR system, validates and transforms the data, and pushes it into the Payroll system.

This is the pattern used in enterprise tools like MuleSoft, Dell Boomi, and SAP Integration Suite — just simplified to its essentials.

---

## Architecture Flow

```
┌─────────────────────┐
│  input/employees.csv│  ← HR System (source)
│  (15 employee rows) │
└────────┬────────────┘
         │ read_employees()
         ▼
┌─────────────────────────────────────────────────────────┐
│                      sync.py                            │
│                                                         │
│  1. read_employees()     — load CSV rows                │
│  2. check_duplicates()   — reject duplicate emp_ids     │
│  3. validate_record()    — check fields, date, salary   │
│  4. transform_record()   — fix types, uppercase country │
│  5. retry_send()         — POST (new) or PUT (exists)   │
└──────────┬────────────────────────┬────────────────────┘
           │ Valid records          │ Invalid records
           ▼                        ▼
┌─────────────────────┐   ┌──────────────────────────┐
│  payroll_api.py     │   │  output/error_log.csv    │
│  REST API           │   │  (emp_id, name, reason,  │
│  POST/PUT /employees│   │   timestamp)             │
└──────────┬──────────┘   └──────────────────────────┘
           │
           ▼
┌─────────────────────┐
│  payroll.db         │  ← SQLite database (Payroll System)
│  employees table    │
└─────────────────────┘
           │
           └──→ logs/sync.log  (timestamped INFO/ERROR)
```

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Sync script | Python 3 | Simple, readable, widely used in integration |
| Payroll API | Flask | Lightweight REST framework for Python |
| Database | SQLite (sqlite3 module) | Zero-config file-based DB, built into Python |
| HTTP client | requests | Simple, readable API calls |
| CSV reading | csv module | Built-in, no dependencies |
| Logging | logging module | Built-in, timestamped log files |
| Tests | pytest | Industry-standard Python test framework |

---

## Project Structure

```
employee-payroll-sync/
├── input/
│   └── employees.csv        ← HR system data (source)
├── output/
│   └── error_log.csv        ← Auto-generated: failed records
├── logs/
│   └── sync.log             ← Auto-generated: timestamped run log
├── payroll_api.py           ← Flask REST API (the payroll system)
├── sync.py                  ← Integration/sync script (the middleware)
├── config.py                ← Central settings (URLs, paths, retries)
├── tests/
│   ├── test_sync.py         ← Unit tests for validation & transform
│   └── test_api.py          ← Integration tests for REST API endpoints
├── docs/
│   └── test_plan.md         ← Test plan with 20 test cases + report
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Clone / download the project

```bash
cd "Employee-to-Payroll Data Sync"
```

### 2. (Optional but recommended) Create a virtual environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# or
source venv/bin/activate     # macOS / Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## How to Run

You need **two terminals** open at the same time:

### Terminal 1 — Start the Payroll API

```bash
python payroll_api.py
```

You should see:
```
 * Running on http://127.0.0.1:5000
 * Database initialised — 'employees' table is ready.
```

### Terminal 2 — Run the Sync Script

```bash
python sync.py
```

You should see output like:
```
2025-06-15 10:23:45,123 - INFO - Read 15 records from input/employees.csv
2025-06-15 10:23:45,130 - WARNING - Duplicate emp_id detected: 102
2025-06-15 10:23:45,145 - INFO - [POST] Employee 101 created in payroll.
...
────────────────────────────────────────
  SYNC COMPLETE
  Total read : 15
  Sent       : 10
  Failed     : 5
────────────────────────────────────────
```

---

## Sample Input (`input/employees.csv`)

```csv
emp_id,name,doj,country,salary,bank_account
101,Alice Johnson,2022-03-15,India,75000,ACC1001
102,Bob Smith,2021-07-20,USA,95000,ACC1002
...
102,Duplicate Bob,2021-07-20,USA,95000,ACC9999      ← duplicate
112,Missing DOJ,,India,60000,ACC1012                ← missing doj
113,Negative Salary,2022-05-10,Canada,-5000,ACC1013 ← bad salary
114,Bad Date Format,2022/13/45,Germany,72000,ACC1014← bad date
115,Missing Account,2023-02-28,Singapore,81000,     ← missing bank_account
```

---

## Sample Output (`output/error_log.csv`)

After a sync run, the error log will look like:

```csv
emp_id,name,reason,timestamp
102,Duplicate Bob,Duplicate emp_id,2025-06-15 10:23:45
112,Missing DOJ,Missing or empty field: 'doj',2025-06-15 10:23:45
113,Negative Salary,"Salary must be greater than 0 (got -5000.0)",2025-06-15 10:23:46
114,Bad Date Format,"Invalid date format or value: '2022/13/45'",2025-06-15 10:23:46
115,Missing Account,Missing or empty field: 'bank_account',2025-06-15 10:23:46
```

---

## Error Handling

| Error Scenario | How It's Handled |
|---------------|-----------------|
| Input CSV file not found | Logs error, returns empty list, prints summary of 0 records |
| Missing mandatory field | Record skipped, written to `error_log.csv` |
| Invalid date format | Record skipped, written to `error_log.csv` |
| Negative or zero salary | Record skipped, written to `error_log.csv` |
| Duplicate emp_id in file | Second+ occurrence skipped, written to `error_log.csv` |
| API is temporarily down | `retry_send` retries up to 3× with 2-second delay |
| API returns 409 (duplicate) | Treated as non-retryable; written to `error_log.csv` |
| `output/` directory missing | Created automatically with `os.makedirs(exist_ok=True)` |

---

## How to Run Tests

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run only sync validation tests
pytest tests/test_sync.py -v

# Run only API endpoint tests
pytest tests/test_api.py -v
```

Expected output:
```
tests/test_sync.py::TestCheckMandatoryFields::test_all_fields_present_returns_valid PASSED
tests/test_sync.py::TestCheckMandatoryFields::test_missing_emp_id_returns_invalid PASSED
...
tests/test_api.py::TestPostEmployee::test_create_valid_employee_returns_201 PASSED
...
====== 36 passed in 0.45s ======
```

---

## Key Concepts Explained

### What is an "upsert"?
The sync script does a **GET first**, then:
- If the employee is **not found** → `POST` (create)
- If the employee **already exists** → `PUT` (update)

This means you can run the sync multiple times safely — no duplicate records.

### Why `?` placeholders in SQL?
```python
# SAFE — uses parameterised query
conn.execute("SELECT * FROM employees WHERE emp_id = ?", (emp_id,))

# UNSAFE — never do this! Vulnerable to SQL injection
conn.execute(f"SELECT * FROM employees WHERE emp_id = {emp_id}")
```

### What is a soft delete?
Instead of `DELETE FROM employees WHERE emp_id = ?`, we run:
```sql
UPDATE employees SET status = 'LEFT' WHERE emp_id = ?
```
This preserves the audit history — you can always see who was in the system.

---

## Interview Talking Points

> "This project simulates an **HR-to-Payroll integration** — a very common enterprise pattern. The sync script acts as middleware: it reads from a source system (CSV), validates and transforms the data, and pushes it to a target system (REST API). I built in retry logic for transient API failures, soft-delete for audit compliance, and parameterised SQL to prevent SQL injection. The upsert pattern makes the sync idempotent — safe to re-run anytime."
