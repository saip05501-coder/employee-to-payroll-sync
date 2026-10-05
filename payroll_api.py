"""
payroll_api.py — The Payroll REST API (Flask)
=============================================
This file simulates a "Payroll System" as a REST API.
Think of this as the TARGET system we want to push employee data INTO.

It uses:
  - Flask   : lightweight Python web framework to build the API
  - SQLite  : a simple file-based database (payroll.db)
  - sqlite3 : Python's built-in module to talk to SQLite

HOW TO RUN:
    python payroll_api.py
    → starts the server at http://localhost:5000
"""

import sqlite3
import logging
from flask import Flask, request, jsonify
import config  # our central settings file

# ──────────────────────────────────────────────
# App Initialization
# ──────────────────────────────────────────────

# Create the Flask application object
app = Flask(__name__)

# Set up basic logging so Flask errors are visible in the console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Database Helpers
# ──────────────────────────────────────────────

def get_db_connection():
    """
    Open and return a connection to the SQLite database.

    We use row_factory = sqlite3.Row so that each row behaves like a
    dictionary — we can access columns by name instead of index.
    e.g., row["name"] instead of row[1]
    """
    conn = sqlite3.connect(config.DB_FILE)
    conn.row_factory = sqlite3.Row  # lets us do row["column_name"]
    return conn


def init_db():
    """
    Create the 'employees' table if it doesn't already exist.

    This is called once when the Flask app starts up.
    The 'IF NOT EXISTS' guard means running it multiple times is safe.

    Column notes:
      emp_id       : the unique employee ID (primary key)
      name         : full name
      doj          : date of joining in YYYY-MM-DD format
      country      : two/three-letter country code (stored uppercase)
      salary       : annual salary as a floating-point number
      bank_account : bank account number for payroll disbursement
      status       : 'ACTIVE' by default; set to 'LEFT' on soft-delete
    """
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            emp_id       INTEGER PRIMARY KEY,
            name         TEXT    NOT NULL,
            doj          TEXT    NOT NULL,
            country      TEXT    NOT NULL,
            salary       REAL    NOT NULL,
            bank_account TEXT    NOT NULL,
            status       TEXT    DEFAULT 'ACTIVE'
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialised — 'employees' table is ready.")


# ──────────────────────────────────────────────
# Validation Helper
# ──────────────────────────────────────────────

def validate_request(data):
    """
    Validate the JSON body sent with a POST or PUT request.

    Checks:
      1. All mandatory fields are present and not empty.
      2. Salary is a positive number.

    Returns:
      (True, "")         — data is valid
      (False, "reason")  — data is invalid, reason explains why

    Note: We keep validation here (server-side) so the API can
    protect itself even if someone bypasses sync.py and calls it directly.
    """
    required_fields = ["name", "doj", "country", "salary", "bank_account"]

    for field in required_fields:
        # Check the field exists AND is not an empty string after stripping whitespace
        if not data.get(field, ""):
            return False, f"Missing or empty required field: '{field}'"

    # Validate salary — must be a positive number
    try:
        salary = float(data["salary"])
        if salary <= 0:
            return False, "Salary must be greater than 0"
    except (ValueError, TypeError):
        return False, "Salary must be a valid number"

    return True, ""  # everything passed


# ──────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────

@app.route("/employees", methods=["POST"])
def add_employee():
    """
    POST /employees — Add a new employee to the payroll system.

    Expects a JSON body with: emp_id, name, doj, country, salary, bank_account

    Returns:
      201 Created  — employee added successfully
      400 Bad Request — missing/invalid data
      409 Conflict    — emp_id already exists
    """
    data = request.get_json()

    # Reject if no JSON body was sent
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Check for emp_id separately since it's not in validate_request
    if not data.get("emp_id"):
        return jsonify({"error": "Missing required field: 'emp_id'"}), 400

    # Run the reusable validation function
    is_valid, reason = validate_request(data)
    if not is_valid:
        return jsonify({"error": reason}), 400

    try:
        conn = get_db_connection()

        # Check if this emp_id already exists in the database
        existing = conn.execute(
            "SELECT emp_id FROM employees WHERE emp_id = ?",
            (data["emp_id"],)       # ? placeholder — never use f-strings with SQL!
        ).fetchone()

        if existing:
            conn.close()
            return jsonify({"error": f"Employee {data['emp_id']} already exists"}), 409

        # Insert the new employee row
        conn.execute(
            """INSERT INTO employees (emp_id, name, doj, country, salary, bank_account)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                int(data["emp_id"]),
                str(data["name"]).strip(),
                str(data["doj"]).strip(),
                str(data["country"]).strip().upper(),
                float(data["salary"]),
                str(data["bank_account"]).strip(),
            )
        )
        conn.commit()
        conn.close()

        logger.info(f"Employee {data['emp_id']} added to payroll.")
        return jsonify({"message": f"Employee {data['emp_id']} created successfully"}), 201

    except sqlite3.Error as e:
        logger.error(f"Database error on POST /employees: {e}")
        return jsonify({"error": "Database error", "detail": str(e)}), 500


@app.route("/employees", methods=["GET"])
def list_employees():
    """
    GET /employees — List all employees in the payroll system.

    Returns:
      200 OK — JSON array of all employee records
    """
    try:
        conn = get_db_connection()
        rows = conn.execute("SELECT * FROM employees").fetchall()
        conn.close()

        # Convert each sqlite3.Row to a plain dict so jsonify can serialise it
        employees = [dict(row) for row in rows]
        return jsonify(employees), 200

    except sqlite3.Error as e:
        logger.error(f"Database error on GET /employees: {e}")
        return jsonify({"error": "Database error", "detail": str(e)}), 500


@app.route("/employees/<int:emp_id>", methods=["GET"])
def get_employee(emp_id):
    """
    GET /employees/<emp_id> — Fetch a single employee by their ID.

    Returns:
      200 OK        — the employee record as JSON
      404 Not Found — no employee with that ID
    """
    try:
        conn = get_db_connection()
        row = conn.execute(
            "SELECT * FROM employees WHERE emp_id = ?",
            (emp_id,)
        ).fetchone()
        conn.close()

        if row is None:
            return jsonify({"error": f"Employee {emp_id} not found"}), 404

        return jsonify(dict(row)), 200

    except sqlite3.Error as e:
        logger.error(f"Database error on GET /employees/{emp_id}: {e}")
        return jsonify({"error": "Database error", "detail": str(e)}), 500


@app.route("/employees/<int:emp_id>", methods=["PUT"])
def update_employee(emp_id):
    """
    PUT /employees/<emp_id> — Update an existing employee's details.

    Useful for salary changes, country transfers, etc.
    The sync script calls this when an employee already exists in payroll.

    Returns:
      200 OK        — update successful
      400 Bad Request — invalid data
      404 Not Found — employee doesn't exist
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Run the reusable validation function
    is_valid, reason = validate_request(data)
    if not is_valid:
        return jsonify({"error": reason}), 400

    try:
        conn = get_db_connection()

        # Make sure the employee actually exists before trying to update
        existing = conn.execute(
            "SELECT emp_id FROM employees WHERE emp_id = ?",
            (emp_id,)
        ).fetchone()

        if existing is None:
            conn.close()
            return jsonify({"error": f"Employee {emp_id} not found"}), 404

        # Update all editable fields
        conn.execute(
            """UPDATE employees
               SET name = ?, doj = ?, country = ?, salary = ?, bank_account = ?
               WHERE emp_id = ?""",
            (
                str(data["name"]).strip(),
                str(data["doj"]).strip(),
                str(data["country"]).strip().upper(),
                float(data["salary"]),
                str(data["bank_account"]).strip(),
                emp_id,
            )
        )
        conn.commit()
        conn.close()

        logger.info(f"Employee {emp_id} updated in payroll.")
        return jsonify({"message": f"Employee {emp_id} updated successfully"}), 200

    except sqlite3.Error as e:
        logger.error(f"Database error on PUT /employees/{emp_id}: {e}")
        return jsonify({"error": "Database error", "detail": str(e)}), 500


@app.route("/employees/<int:emp_id>", methods=["DELETE"])
def delete_employee(emp_id):
    """
    DELETE /employees/<emp_id> — Soft-delete an employee.

    We NEVER physically remove a row from the database.
    Instead, we set status = 'LEFT' to keep the audit trail.
    This is standard practice in payroll/HR systems.

    Returns:
      200 OK        — status updated to 'LEFT'
      404 Not Found — employee doesn't exist
    """
    try:
        conn = get_db_connection()

        existing = conn.execute(
            "SELECT emp_id FROM employees WHERE emp_id = ?",
            (emp_id,)
        ).fetchone()

        if existing is None:
            conn.close()
            return jsonify({"error": f"Employee {emp_id} not found"}), 404

        conn.execute(
            "UPDATE employees SET status = 'LEFT' WHERE emp_id = ?",
            (emp_id,)
        )
        conn.commit()
        conn.close()

        logger.info(f"Employee {emp_id} marked as LEFT.")
        return jsonify({"message": f"Employee {emp_id} marked as LEFT (soft-deleted)"}), 200

    except sqlite3.Error as e:
        logger.error(f"Database error on DELETE /employees/{emp_id}: {e}")
        return jsonify({"error": "Database error", "detail": str(e)}), 500


# ──────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    # Initialise the database when the server starts
    init_db()

    # Run Flask in debug mode so errors print nicely in the terminal.
    # IMPORTANT: never use debug=True in production!
    app.run(debug=True, port=5000)
