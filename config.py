"""
config.py — Central Configuration File
=======================================
All settings live here so you only need to change ONE place
when you move to a different server, file path, or environment.
Think of this as the "control panel" of the project.
"""

# ──────────────────────────────────────────────
# API Settings
# ──────────────────────────────────────────────

# The base URL of the payroll REST API (Flask app)
# Using 127.0.0.1 avoids IPv6 resolution delays on Windows
API_BASE_URL = "http://127.0.0.1:5000"

# Full endpoint for the employees resource
EMPLOYEES_ENDPOINT = f"{API_BASE_URL}/employees"

# ──────────────────────────────────────────────
# File Paths
# ──────────────────────────────────────────────

# Input CSV: the "HR system" data we read from
INPUT_FILE = "input/employees.csv"

# Output CSV: rows that failed validation or API calls are written here
ERROR_LOG_FILE = "output/error_log.csv"

# Log file: timestamped INFO/ERROR messages from the sync run
LOG_FILE = "logs/sync.log"

# SQLite database used by the payroll API
DB_FILE = "payroll.db"

# ──────────────────────────────────────────────
# Retry Settings
# ──────────────────────────────────────────────

# How many times to retry sending a record if the API returns a server error
RETRY_COUNT = 3

# Seconds to wait between retries (keeps it short for a demo)
RETRY_DELAY = 2  # seconds
