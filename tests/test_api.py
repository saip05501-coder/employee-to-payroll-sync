"""
tests/test_api.py — Integration Tests for payroll_api.py
=========================================================
These tests use Flask's built-in test client — no real network call is made.
The test client simulates HTTP requests directly against the app object.

KEY CONCEPT: Each test gets a FRESH, in-memory SQLite database (:memory:)
so tests don't interfere with each other or the real payroll.db file.

HOW IT WORKS:
  SQLite's ":memory:" creates an in-memory database per-connection.
  To keep the same DB alive for the duration of one test, we patch
  payroll_api.get_db_connection to always return the SAME shared
  connection (instead of opening a new file-based connection each call).

HOW TO RUN:
    pytest tests/test_api.py -v
"""

import pytest
import sqlite3
import sys
import os
from unittest.mock import patch

# Add parent directory so we can import payroll_api
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import payroll_api  # import the Flask app


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """
    Create a Flask test client backed by a fresh in-memory SQLite database.

    Strategy:
      - Open ONE real in-memory SQLite connection per test.
      - Wrap it in NonClosingProxy so route handlers calling conn.close()
        do NOT actually destroy the shared connection between calls.
      - Patch payroll_api.get_db_connection to return the proxy each time.
      - Yield the Flask test client to the test function.
      - After the test, close the real connection for cleanup.

    Python 3.14 note: sqlite3.Connection.close is a read-only slot, so we
    cannot monkey-patch it. The proxy class pattern is the clean solution.
    """
    payroll_api.app.config["TESTING"] = True

    # ── Create ONE shared in-memory connection ──────────────────────────────
    real_conn = sqlite3.connect(":memory:", check_same_thread=False)
    real_conn.row_factory = sqlite3.Row

    # Create the employees table once for this test
    real_conn.execute("""
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
    real_conn.commit()

    # ── Proxy class: delegates everything except close() ────────────────────
    class NonClosingProxy:
        """
        Wraps a sqlite3.Connection and makes close() a no-op.
        This lets Flask route handlers call conn.close() without
        destroying the shared in-memory connection between requests.
        """
        def __init__(self, conn):
            self._conn = conn

        # Intercept close() so it does nothing
        def close(self):
            pass  # intentional no-op

        # Forward every other attribute/method to the real connection
        def __getattr__(self, name):
            return getattr(self._conn, name)

    proxy = NonClosingProxy(real_conn)

    # ── Patch get_db_connection to always return our proxy ──────────────────
    with patch.object(payroll_api, "get_db_connection", return_value=proxy):
        with payroll_api.app.test_client() as test_client:
            yield test_client

    # ── Actual cleanup: close the real connection after the test ─────────────
    real_conn.close()


@pytest.fixture
def sample_employee():
    """A valid employee dict — used as a baseline for POST tests."""
    return {
        "emp_id":       101,
        "name":         "Alice Johnson",
        "doj":          "2022-03-15",
        "country":      "INDIA",
        "salary":       75000.0,
        "bank_account": "ACC1001",
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /employees — Create new employee
# ─────────────────────────────────────────────────────────────────────────────

class TestPostEmployee:
    """Tests for POST /employees endpoint."""

    def test_create_valid_employee_returns_201(self, client, sample_employee):
        """A valid employee payload should return HTTP 201 Created."""
        response = client.post("/employees", json=sample_employee)
        assert response.status_code == 201
        data = response.get_json()
        assert "created" in data["message"].lower()

    def test_create_duplicate_employee_returns_409(self, client, sample_employee):
        """Posting the same emp_id twice should return HTTP 409 Conflict."""
        client.post("/employees", json=sample_employee)   # first time: ok
        response = client.post("/employees", json=sample_employee)  # second: conflict
        assert response.status_code == 409
        assert "already exists" in response.get_json()["error"].lower()

    def test_create_with_missing_name_returns_400(self, client, sample_employee):
        """Missing 'name' field should return HTTP 400 Bad Request."""
        sample_employee["name"] = ""
        response = client.post("/employees", json=sample_employee)
        assert response.status_code == 400

    def test_create_with_missing_emp_id_returns_400(self, client, sample_employee):
        """Missing 'emp_id' should return HTTP 400."""
        del sample_employee["emp_id"]
        response = client.post("/employees", json=sample_employee)
        assert response.status_code == 400

    def test_create_with_negative_salary_returns_400(self, client, sample_employee):
        """Negative salary should return HTTP 400."""
        sample_employee["salary"] = -500
        response = client.post("/employees", json=sample_employee)
        assert response.status_code == 400
        assert "salary" in response.get_json()["error"].lower()

    def test_create_with_zero_salary_returns_400(self, client, sample_employee):
        """Zero salary should return HTTP 400."""
        sample_employee["salary"] = 0
        response = client.post("/employees", json=sample_employee)
        assert response.status_code == 400

    def test_create_with_no_body_returns_400(self, client):
        """Sending a non-JSON body should return a 4xx client error.

        Flask 3.x returns 415 (Unsupported Media Type) when the content-type
        is not application/json. Earlier versions returned 400. Both are valid
        client-error responses, so we check for the 4xx range.
        """
        response = client.post("/employees", data="not json",
                               content_type="text/plain")
        assert 400 <= response.status_code < 500, (
            f"Expected a 4xx client error, got {response.status_code}"
        )

    def test_create_with_missing_bank_account_returns_400(self, client, sample_employee):
        """Missing bank_account should return HTTP 400."""
        sample_employee["bank_account"] = ""
        response = client.post("/employees", json=sample_employee)
        assert response.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# GET /employees — List all employees
# ─────────────────────────────────────────────────────────────────────────────

class TestGetAllEmployees:
    """Tests for GET /employees endpoint."""

    def test_empty_db_returns_empty_list(self, client):
        """With no data, should return HTTP 200 and an empty list."""
        response = client.get("/employees")
        assert response.status_code == 200
        assert response.get_json() == []

    def test_returns_all_inserted_employees(self, client, sample_employee):
        """After inserting 2 employees, GET should return both."""
        client.post("/employees", json=sample_employee)
        emp2 = sample_employee.copy()
        emp2["emp_id"] = 102
        emp2["name"] = "Bob Smith"
        client.post("/employees", json=emp2)

        response = client.get("/employees")
        assert response.status_code == 200
        employees = response.get_json()
        assert len(employees) == 2


# ─────────────────────────────────────────────────────────────────────────────
# GET /employees/<emp_id> — Fetch single employee
# ─────────────────────────────────────────────────────────────────────────────

class TestGetOneEmployee:
    """Tests for GET /employees/<emp_id> endpoint."""

    def test_get_existing_employee_returns_200(self, client, sample_employee):
        """Fetching an existing employee should return HTTP 200 with data."""
        client.post("/employees", json=sample_employee)
        response = client.get("/employees/101")
        assert response.status_code == 200
        data = response.get_json()
        assert data["emp_id"] == 101
        assert data["name"] == "Alice Johnson"

    def test_get_nonexistent_employee_returns_404(self, client):
        """Fetching an emp_id that doesn't exist should return HTTP 404."""
        response = client.get("/employees/9999")
        assert response.status_code == 404
        assert "not found" in response.get_json()["error"].lower()

    def test_get_returns_correct_salary(self, client, sample_employee):
        """The returned salary should match what was inserted."""
        client.post("/employees", json=sample_employee)
        response = client.get("/employees/101")
        assert response.get_json()["salary"] == 75000.0


# ─────────────────────────────────────────────────────────────────────────────
# PUT /employees/<emp_id> — Update employee
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateEmployee:
    """Tests for PUT /employees/<emp_id> endpoint."""

    def test_update_existing_employee_returns_200(self, client, sample_employee):
        """Updating an existing employee with valid data returns HTTP 200."""
        client.post("/employees", json=sample_employee)
        updated = sample_employee.copy()
        updated["salary"] = 90000.0
        response = client.put("/employees/101", json=updated)
        assert response.status_code == 200

    def test_update_actually_changes_salary(self, client, sample_employee):
        """After a PUT, the GET should return the new salary."""
        client.post("/employees", json=sample_employee)
        updated = sample_employee.copy()
        updated["salary"] = 90000.0
        client.put("/employees/101", json=updated)
        get_response = client.get("/employees/101")
        assert get_response.get_json()["salary"] == 90000.0

    def test_update_nonexistent_employee_returns_404(self, client, sample_employee):
        """Trying to update an employee who doesn't exist returns HTTP 404."""
        response = client.put("/employees/9999", json=sample_employee)
        assert response.status_code == 404

    def test_update_with_invalid_salary_returns_400(self, client, sample_employee):
        """Updating with a negative salary returns HTTP 400."""
        client.post("/employees", json=sample_employee)
        invalid = sample_employee.copy()
        invalid["salary"] = -100
        response = client.put("/employees/101", json=invalid)
        assert response.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /employees/<emp_id> — Soft-delete (status → 'LEFT')
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteEmployee:
    """Tests for DELETE /employees/<emp_id> endpoint."""

    def test_delete_existing_employee_returns_200(self, client, sample_employee):
        """Soft-deleting an existing employee returns HTTP 200."""
        client.post("/employees", json=sample_employee)
        response = client.delete("/employees/101")
        assert response.status_code == 200
        assert "LEFT" in response.get_json()["message"]

    def test_delete_sets_status_to_left(self, client, sample_employee):
        """After DELETE, the employee's status should be 'LEFT' not 'ACTIVE'."""
        client.post("/employees", json=sample_employee)
        client.delete("/employees/101")
        get_response = client.get("/employees/101")
        assert get_response.get_json()["status"] == "LEFT"

    def test_delete_nonexistent_employee_returns_404(self, client):
        """Soft-deleting an employee who doesn't exist returns HTTP 404."""
        response = client.delete("/employees/9999")
        assert response.status_code == 404

    def test_record_still_exists_after_soft_delete(self, client, sample_employee):
        """After DELETE, the record should still be retrievable via GET."""
        client.post("/employees", json=sample_employee)
        client.delete("/employees/101")
        # The record should still be there (soft-delete, not hard-delete)
        get_response = client.get("/employees/101")
        assert get_response.status_code == 200  # not 404
