"""
sync.py — The Integration / Sync Script
=========================================
This is the HEART of the project. It acts as the middleware/integration layer
that bridges the HR system (CSV file) and the Payroll system (REST API).

Flow:
  1. Read employee records from input/employees.csv
  2. Check for duplicate emp_ids within the file
  3. Validate each record (mandatory fields, date format, salary)
  4. Transform the record into the payroll API's expected format
  5. Send to payroll API — POST (new) or PUT (update existing)
  6. On failure: write to output/error_log.csv
  7. Print a summary of Total / Success / Failed counts

HOW TO RUN (after payroll_api.py is already running):
    python sync.py
"""

import csv
import logging
import os
import time
from datetime import datetime, date

import requests

import config  # our central settings file

# ──────────────────────────────────────────────
# Logging Setup
# ──────────────────────────────────────────────

def setup_logging():
    """
    Configure the Python logging module.

    - Writes timestamped log lines to logs/sync.log
    - Also mirrors log output to the console (StreamHandler)
    - Log level INFO means we capture INFO, WARNING, ERROR, CRITICAL

    Example log line:
      2025-06-15 10:23:45,123 - INFO - Employee 101 sent successfully.
    """
    # Make sure the logs/ directory exists before trying to write to it
    os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            # Write to file
            logging.FileHandler(config.LOG_FILE),
            # Also print to console
            logging.StreamHandler(),
        ],
    )

# Call setup_logging immediately so the logger is ready for the whole module
setup_logging()
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Step 1 — Read
# ──────────────────────────────────────────────

def read_employees(file_path):
    """
    Read employee records from a CSV file and return them as a list of dicts.

    The csv.DictReader automatically uses the first row as column headers,
    so each row becomes {"emp_id": "101", "name": "Alice", ...}.

    Args:
        file_path (str): Path to the CSV file (e.g., "input/employees.csv")

    Returns:
        list[dict]: A list of employee records, or an empty list on error.
    """
    records = []

    # Guard: make sure the file actually exists before trying to open it
    if not os.path.exists(file_path):
        logger.error(f"Input file not found: {file_path}")
        return records

    try:
        # 'newline=""' is recommended by Python docs when reading CSVs
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Strip leading/trailing whitespace from every value
                cleaned = {k: v.strip() for k, v in row.items()}
                records.append(cleaned)

        logger.info(f"Read {len(records)} records from {file_path}")

    except Exception as e:
        logger.error(f"Failed to read {file_path}: {e}")

    return records


# ──────────────────────────────────────────────
# Step 2 — Duplicate Detection
# ──────────────────────────────────────────────

def check_duplicates(records):
    """
    Detect duplicate emp_id values within the CSV file.

    Strategy:
      - Walk through records in order, keeping track of emp_ids we've seen.
      - If an emp_id appears more than once, mark the LATER occurrence as a duplicate.
      - The first occurrence is kept valid; subsequent ones are flagged.

    Args:
        records (list[dict]): All records read from the CSV.

    Returns:
        tuple:
          - valid (list[dict]): Records with unique emp_ids.
          - duplicates (list[tuple]): (record, reason) pairs for duplicates.
    """
    seen_ids = set()   # set is O(1) for lookup — fast even with many records
    valid = []
    duplicates = []

    for record in records:
        emp_id = record.get("emp_id", "").strip()

        if emp_id in seen_ids:
            # This is the second (or later) occurrence — mark it as a duplicate
            duplicates.append((record, "Duplicate emp_id"))
            logger.warning(f"Duplicate emp_id detected: {emp_id}")
        else:
            # First time we see this emp_id — it's safe
            seen_ids.add(emp_id)
            valid.append(record)

    return valid, duplicates


# ──────────────────────────────────────────────
# Step 3 — Validation Helpers
# ──────────────────────────────────────────────

def check_mandatory_fields(record):
    """
    Check that all required fields are present and non-empty.

    Required fields: emp_id, name, doj, country, salary, bank_account

    Args:
        record (dict): A single employee record.

    Returns:
        tuple: (True, "") if all fields are present,
               (False, "reason string") if any field is missing or empty.
    """
    required = ["emp_id", "name", "doj", "country", "salary", "bank_account"]

    for field in required:
        value = record.get(field, "").strip()
        if not value:
            return False, f"Missing or empty field: '{field}'"

    return True, ""


def parse_date(date_str):
    """
    Parse a date string from various common formats:
      - Primary standard: DD/MM/YYYY (e.g., "15/03/2022")
      - Also accepts: DD-MM-YYYY, YYYY-MM-DD, YYYY/MM/DD

    Returns:
        date or None: The parsed datetime.date object, or None if invalid.
    """
    formats = [
        "%d/%m/%Y",  # Primary standard CSV format: DD/MM/YYYY (e.g. 15/03/2022)
        "%d-%m-%Y",  # Hyphen format: DD-MM-YYYY (e.g. 15-03-2022)
        "%Y-%m-%d",  # ISO standard: YYYY-MM-DD (e.g. 2022-03-15)
        "%Y/%m/%d",  # YYYY/MM/DD (e.g. 2022/03/15)
    ]
    if not date_str:
        return None
    cleaned = date_str.strip()
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def check_date_format(date_str):
    """
    Validate that a date string is:
      1. In a recognised date format (standard DD/MM/YYYY, or DD-MM-YYYY / YYYY-MM-DD)
      2. Not a future date (doj can't be tomorrow or later)

    Args:
        date_str (str): The date string to validate.

    Returns:
        tuple: (True, "") if valid, (False, "reason") if invalid.
    """
    if not date_str or not date_str.strip():
        return False, "Date is empty"

    parsed_date = parse_date(date_str)
    if not parsed_date:
        return False, f"Invalid date format or value: '{date_str}' (expected DD/MM/YYYY)"

    # Business rule: date of joining cannot be in the future
    if parsed_date > date.today():
        return False, f"Date of joining '{date_str}' is in the future"

    return True, ""


def check_salary(salary_str):
    """
    Validate that salary is a number greater than zero.

    Args:
        salary_str (str): The raw salary string from the CSV.

    Returns:
        tuple: (True, "") if valid, (False, "reason") if invalid.
    """
    try:
        salary = float(salary_str)
    except (ValueError, TypeError):
        return False, f"Salary '{salary_str}' is not a valid number"

    if salary <= 0:
        return False, f"Salary must be greater than 0 (got {salary})"

    return True, ""


def validate_record(record):
    """
    Master validation function — runs all checks on a single record.

    Order of checks:
      1. Mandatory fields (fail-fast: no point checking date if doj is empty)
      2. Date format and future-date check
      3. Salary value check

    Args:
        record (dict): A single employee record.

    Returns:
        tuple: (True, "") if the record passes ALL checks,
               (False, "reason") with the FIRST failure reason found.
    """
    # Check 1: mandatory fields
    valid, reason = check_mandatory_fields(record)
    if not valid:
        return False, reason

    # Check 2: date of joining format
    valid, reason = check_date_format(record["doj"])
    if not valid:
        return False, reason

    # Check 3: salary value
    valid, reason = check_salary(record["salary"])
    if not valid:
        return False, reason

    # All checks passed
    return True, ""


# ──────────────────────────────────────────────
# Step 4 — Transform
# ──────────────────────────────────────────────

def transform_record(record):
    """
    Convert a raw CSV record (all strings) into the format expected by the
    Payroll API (correct Python types, normalised values).

    Transformations applied:
      - emp_id  : str → int
      - salary  : str → float
      - country : any case → UPPERCASE (e.g., "india" → "INDIA")
      - name    : trim leading/trailing spaces
      - doj     : normalise date to standard ISO YYYY-MM-DD
      - bank_account: trim spaces

    Args:
        record (dict): Raw string record from the CSV.

    Returns:
        dict: Transformed record ready to send to the API.
    """
    parsed_date = parse_date(record["doj"])
    normalized_doj = parsed_date.strftime("%Y-%m-%d") if parsed_date else record["doj"].strip()

    return {
        "emp_id":       int(record["emp_id"]),
        "name":         record["name"].strip(),
        "doj":          normalized_doj,
        "country":      record["country"].strip().upper(),
        "salary":       float(record["salary"]),
        "bank_account": record["bank_account"].strip(),
    }


# ──────────────────────────────────────────────
# Step 5 — Send to API (upsert logic)
# ──────────────────────────────────────────────

def send_to_payroll(record):
    """
    Send a transformed employee record to the Payroll API.

    This implements an "upsert" pattern:
      - First, check if the employee already exists using GET /employees/<id>
      - If NOT found → POST /employees  (create new)
      - If FOUND     → PUT /employees/<id>  (update existing)

    This makes the sync idempotent: you can run it multiple times and it
    won't create duplicate rows; it just updates existing ones.

    Args:
        record (dict): Transformed employee record.

    Returns:
        tuple: (True, "success message") on success,
               (False, "error message") on failure.
    """
    emp_id = record["emp_id"]
    get_url = f"{config.EMPLOYEES_ENDPOINT}/{emp_id}"
    post_url = config.EMPLOYEES_ENDPOINT
    put_url = get_url

    try:
        # Step A: Check if the employee already exists
        get_response = requests.get(get_url, timeout=10)

        if get_response.status_code == 404:
            # Employee doesn't exist — create it with POST
            post_response = requests.post(post_url, json=record, timeout=10)

            if post_response.status_code == 201:
                logger.info(f"[POST] Employee {emp_id} created in payroll.")
                return True, f"Employee {emp_id} created (201)"
            else:
                # API returned an error — extract the message
                error_msg = post_response.json().get("error", post_response.text)
                logger.error(f"[POST] Failed for emp_id {emp_id}: {error_msg}")
                return False, error_msg

        elif get_response.status_code == 200:
            # Employee already exists — update it with PUT
            put_response = requests.put(put_url, json=record, timeout=10)

            if put_response.status_code == 200:
                logger.info(f"[PUT] Employee {emp_id} updated in payroll.")
                return True, f"Employee {emp_id} updated (200)"
            else:
                error_msg = put_response.json().get("error", put_response.text)
                logger.error(f"[PUT] Failed for emp_id {emp_id}: {error_msg}")
                return False, error_msg

        else:
            # Unexpected status code from the GET call
            logger.error(f"Unexpected GET status {get_response.status_code} for emp_id {emp_id}")
            return False, f"Unexpected GET status: {get_response.status_code}"

    except requests.exceptions.ConnectionError:
        # The API server is not running or unreachable
        raise  # re-raise so retry_send can catch it and retry

    except requests.exceptions.Timeout:
        raise  # re-raise for retry

    except Exception as e:
        logger.error(f"Unexpected error sending emp_id {emp_id}: {e}")
        return False, str(e)


def retry_send(record, retries=None, delay=None):
    """
    Wrapper around send_to_payroll that retries on connection errors or server
    errors (5xx HTTP status codes).

    Why retry?
      In real integrations, APIs can be briefly unavailable due to restarts,
      network blips, or high load. Retrying a few times prevents temporary
      issues from causing permanent failures.

    Args:
        record  (dict): Transformed employee record.
        retries (int) : Number of attempts (defaults to config.RETRY_COUNT).
        delay   (int) : Seconds between attempts (defaults to config.RETRY_DELAY).

    Returns:
        tuple: (True, "message") on success, (False, "reason") after all retries fail.
    """
    if retries is None:
        retries = config.RETRY_COUNT
    if delay is None:
        delay = config.RETRY_DELAY

    last_error = "Unknown error"

    for attempt in range(1, retries + 1):
        try:
            success, message = send_to_payroll(record)
            if success:
                return True, message

            # API returned a non-success response (client error like 400/409)
            # These are NOT worth retrying — wrong data won't become right later
            return False, message

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_error = str(e)
            logger.warning(
                f"Attempt {attempt}/{retries} failed for emp_id "
                f"{record.get('emp_id')}: {e}"
            )
            if attempt < retries:
                logger.info(f"Retrying in {delay} second(s)...")
                time.sleep(delay)

    # All retries exhausted
    logger.error(
        f"All {retries} attempts failed for emp_id {record.get('emp_id')}."
    )
    return False, f"API unreachable after {retries} attempts: {last_error}"


# ──────────────────────────────────────────────
# Step 6 — Error Logging
# ──────────────────────────────────────────────

def write_error_log(record, reason):
    """
    Append a failed record to the error log CSV file.

    The error log is a CSV with columns:
      emp_id | name | reason | timestamp

    We APPEND (mode 'a') so each run adds its failures without erasing
    the previous run's failures. If the file doesn't exist, we create it
    and write the header first.

    Args:
        record (dict): The employee record that failed.
        reason (str) : Why it failed (validation message or API error).
    """
    # Make sure the output/ directory exists
    os.makedirs(os.path.dirname(config.ERROR_LOG_FILE), exist_ok=True)

    # Check if the file already exists — if not, we need to write the header
    file_exists = os.path.exists(config.ERROR_LOG_FILE)

    try:
        with open(config.ERROR_LOG_FILE, "a", newline="", encoding="utf-8") as f:
            fieldnames = ["emp_id", "name", "reason", "timestamp"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            # Write header only if this is a brand-new file
            if not file_exists:
                writer.writeheader()

            writer.writerow({
                "emp_id":    record.get("emp_id", ""),
                "name":      record.get("name", ""),
                "reason":    reason,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

    except Exception as e:
        # If we can't write the error log, at least log it to the console
        logger.error(f"Could not write to error log: {e}")


# ──────────────────────────────────────────────
# Step 7 — Summary
# ──────────────────────────────────────────────

def generate_summary(total, success, failed):
    """
    Print and log the sync run summary.

    Args:
        total   (int): Total records read from CSV.
        success (int): Records successfully sent to the API.
        failed  (int): Records that failed validation or API calls.
    """
    summary = (
        f"----------------------------------------\n"
        f"  SYNC COMPLETE\n"
        f"  Total read : {total}\n"
        f"  Sent       : {success}\n"
        f"  Failed     : {failed}\n"
        f"----------------------------------------"
    )
    print(summary)
    logger.info(f"Total read: {total} | Sent: {success} | Failed: {failed}")


# ──────────────────────────────────────────────
# Main Orchestrator
# ──────────────────────────────────────────────

def main():
    """
    Orchestrate the full sync pipeline:

    1. Read all employee records from the CSV.
    2. Detect and separate in-file duplicates.
    3. For each unique record:
       a. Validate it (mandatory fields, date, salary).
       b. If invalid → log to error CSV, skip.
       c. If valid   → transform → send with retry.
       d. If send fails → log to error CSV.
    4. Count successes and failures.
    5. Print / log the summary.
    """
    logger.info("=" * 50)
    logger.info("Starting Employee-to-Payroll Sync")
    logger.info("=" * 50)

    # ── Step 1: Read ──────────────────────────────────
    records = read_employees(config.INPUT_FILE)

    if not records:
        logger.error("No records to process. Exiting.")
        return

    total = len(records)
    success_count = 0
    failed_count = 0

    # ── Step 2: Duplicate check ───────────────────────
    unique_records, duplicate_records = check_duplicates(records)

    # Log/count duplicates immediately
    for dup_record, reason in duplicate_records:
        logger.warning(f"Skipping duplicate emp_id {dup_record.get('emp_id')}: {reason}")
        write_error_log(dup_record, reason)
        failed_count += 1

    # ── Step 3–6: Validate → Transform → Send ─────────
    for record in unique_records:

        # 3a. Validate
        is_valid, reason = validate_record(record)

        if not is_valid:
            logger.warning(f"Validation failed for emp_id {record.get('emp_id')}: {reason}")
            write_error_log(record, reason)
            failed_count += 1
            continue  # skip to next record

        # 3b. Transform — convert types and normalise values
        try:
            transformed = transform_record(record)
        except Exception as e:
            # This should rarely happen since validate_record already checked
            # types, but we handle it defensively
            reason = f"Transform error: {e}"
            logger.error(f"emp_id {record.get('emp_id')}: {reason}")
            write_error_log(record, reason)
            failed_count += 1
            continue

        # 3c. Send with retry
        sent, message = retry_send(transformed)

        if sent:
            success_count += 1
        else:
            write_error_log(record, message)
            failed_count += 1

    # ── Step 7: Summary ───────────────────────────────
    generate_summary(total, success_count, failed_count)


# ──────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    main()
