"""
tests/test_sync.py — Unit Tests for sync.py
=============================================
We test each validation function in isolation using pytest.

KEY CONCEPT: Unit tests test one function at a time with known inputs
and check that the output matches what we expect. We don't call the
real API or read real files here — we just test the logic.

HOW TO RUN:
    pytest tests/test_sync.py -v
    (the -v flag gives you a detailed pass/fail list per test)
"""

import pytest
import sys
import os

# Make sure Python can find sync.py (it's in the parent directory)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sync import (
    check_mandatory_fields,
    check_date_format,
    check_salary,
    validate_record,
    check_duplicates,
    transform_record,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — shared sample data used across multiple tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def valid_record():
    """A complete, valid employee record — used as a baseline."""
    return {
        "emp_id":       "101",
        "name":         "Alice Johnson",
        "doj":          "2022-03-15",
        "country":      "India",
        "salary":       "75000",
        "bank_account": "ACC1001",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tests for check_mandatory_fields()
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckMandatoryFields:
    """Tests for the mandatory-field presence check."""

    def test_all_fields_present_returns_valid(self, valid_record):
        """A complete record should pass with no reason."""
        is_valid, reason = check_mandatory_fields(valid_record)
        assert is_valid is True
        assert reason == ""

    def test_missing_emp_id_returns_invalid(self, valid_record):
        """emp_id is required — removing it should fail."""
        valid_record["emp_id"] = ""
        is_valid, reason = check_mandatory_fields(valid_record)
        assert is_valid is False
        assert "emp_id" in reason

    def test_missing_name_returns_invalid(self, valid_record):
        """name is required — removing it should fail."""
        valid_record["name"] = ""
        is_valid, reason = check_mandatory_fields(valid_record)
        assert is_valid is False
        assert "name" in reason

    def test_missing_doj_returns_invalid(self, valid_record):
        """doj is required — removing it should fail."""
        valid_record["doj"] = ""
        is_valid, reason = check_mandatory_fields(valid_record)
        assert is_valid is False
        assert "doj" in reason

    def test_missing_country_returns_invalid(self, valid_record):
        """country is required — removing it should fail."""
        valid_record["country"] = ""
        is_valid, reason = check_mandatory_fields(valid_record)
        assert is_valid is False
        assert "country" in reason

    def test_missing_salary_returns_invalid(self, valid_record):
        """salary is required — removing it should fail."""
        valid_record["salary"] = ""
        is_valid, reason = check_mandatory_fields(valid_record)
        assert is_valid is False
        assert "salary" in reason

    def test_missing_bank_account_returns_invalid(self, valid_record):
        """bank_account is required — removing it should fail."""
        valid_record["bank_account"] = ""
        is_valid, reason = check_mandatory_fields(valid_record)
        assert is_valid is False
        assert "bank_account" in reason

    def test_whitespace_only_field_counts_as_missing(self, valid_record):
        """A field with only spaces should be treated as missing."""
        valid_record["name"] = "   "
        is_valid, reason = check_mandatory_fields(valid_record)
        assert is_valid is False

    def test_field_not_in_record_at_all(self):
        """A record missing a key entirely should fail."""
        incomplete = {
            "emp_id": "101",
            "name":   "Alice",
            # doj, country, salary, bank_account are missing
        }
        is_valid, reason = check_mandatory_fields(incomplete)
        assert is_valid is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests for check_date_format()
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckDateFormat:
    """Tests for date format and future-date validation."""

    def test_valid_date_passes(self):
        """A properly formatted past date should pass."""
        is_valid, reason = check_date_format("2022-03-15")
        assert is_valid is True
        assert reason == ""

    def test_future_date_fails(self):
        """A date in the future must be rejected."""
        is_valid, reason = check_date_format("2099-01-01")
        assert is_valid is False
        assert "future" in reason.lower()

    def test_standard_dd_mm_yyyy_with_slashes_passes(self):
        """Standard DD/MM/YYYY format passes validation."""
        is_valid, reason = check_date_format("15/03/2022")
        assert is_valid is True
        assert reason == ""

    def test_dd_mm_yyyy_format_is_accepted(self):
        """DD-MM-YYYY format is also accepted and parsed."""
        is_valid, reason = check_date_format("15-03-2022")
        assert is_valid is True
        assert reason == ""

    def test_slash_separated_date_is_accepted(self):
        """Slashes (e.g. DD/MM/YYYY or YYYY/MM/DD) are accepted."""
        is_valid, reason = check_date_format("2022/03/15")
        assert is_valid is True
        assert reason == ""

    def test_impossible_month_fails(self):
        """Month 13 doesn't exist."""
        is_valid, reason = check_date_format("2022-13-01")
        assert is_valid is False

    def test_impossible_day_fails(self):
        """Day 45 doesn't exist in any month."""
        is_valid, reason = check_date_format("2022/13/45")
        assert is_valid is False

    def test_empty_string_fails(self):
        """Empty string is not a valid date."""
        is_valid, reason = check_date_format("")
        assert is_valid is False

    def test_today_is_valid(self):
        """Today's date is a valid doj — it's not in the future."""
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        is_valid, reason = check_date_format(today)
        assert is_valid is True

    def test_text_instead_of_date_fails(self):
        """A plain text string is not a date."""
        is_valid, reason = check_date_format("not-a-date")
        assert is_valid is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests for check_salary()
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckSalary:
    """Tests for salary validation (numeric, positive)."""

    def test_positive_integer_salary_passes(self):
        """A regular positive integer salary should pass."""
        is_valid, reason = check_salary("75000")
        assert is_valid is True

    def test_positive_float_salary_passes(self):
        """Floats are valid salaries too."""
        is_valid, reason = check_salary("75000.50")
        assert is_valid is True

    def test_negative_salary_fails(self):
        """Negative salary is never valid."""
        is_valid, reason = check_salary("-5000")
        assert is_valid is False
        assert "greater than 0" in reason

    def test_zero_salary_fails(self):
        """Zero salary is not valid (must be > 0)."""
        is_valid, reason = check_salary("0")
        assert is_valid is False

    def test_text_salary_fails(self):
        """Non-numeric salary must fail."""
        is_valid, reason = check_salary("seventy-five thousand")
        assert is_valid is False

    def test_empty_salary_fails(self):
        """Empty string is not a valid salary."""
        is_valid, reason = check_salary("")
        assert is_valid is False

    def test_salary_with_currency_symbol_fails(self):
        """Salary with '$' prefix is not parseable as float."""
        is_valid, reason = check_salary("$75000")
        assert is_valid is False

    def test_very_large_salary_passes(self):
        """Large salaries (e.g., executives) are valid."""
        is_valid, reason = check_salary("9999999")
        assert is_valid is True

    def test_small_positive_salary_passes(self):
        """Even a very small positive salary (e.g., 0.01) is valid."""
        is_valid, reason = check_salary("0.01")
        assert is_valid is True


# ─────────────────────────────────────────────────────────────────────────────
# Tests for validate_record() — the master validation function
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateRecord:
    """Tests for the combined validate_record() function."""

    def test_fully_valid_record_passes(self, valid_record):
        """A record that passes all checks should return (True, '')."""
        is_valid, reason = validate_record(valid_record)
        assert is_valid is True
        assert reason == ""

    def test_invalid_date_fails_validation(self, valid_record):
        """An invalid date causes validate_record to fail."""
        valid_record["doj"] = "not-a-date"
        is_valid, reason = validate_record(valid_record)
        assert is_valid is False

    def test_invalid_salary_fails_validation(self, valid_record):
        """A negative salary causes validate_record to fail."""
        valid_record["salary"] = "-100"
        is_valid, reason = validate_record(valid_record)
        assert is_valid is False

    def test_missing_field_fails_before_date_check(self, valid_record):
        """Mandatory field check runs first; date check is skipped."""
        valid_record["doj"] = ""  # empty — fails mandatory check
        is_valid, reason = validate_record(valid_record)
        assert is_valid is False
        assert "doj" in reason  # should say 'missing doj', not a date format error


# ─────────────────────────────────────────────────────────────────────────────
# Tests for check_duplicates()
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckDuplicates:
    """Tests for duplicate emp_id detection within a batch of records."""

    def test_no_duplicates_returns_all_valid(self):
        """All unique emp_ids → everything comes back as valid."""
        records = [
            {"emp_id": "101", "name": "Alice"},
            {"emp_id": "102", "name": "Bob"},
            {"emp_id": "103", "name": "Carol"},
        ]
        valid, dupes = check_duplicates(records)
        assert len(valid) == 3
        assert len(dupes) == 0

    def test_duplicate_emp_id_is_flagged(self):
        """Second occurrence of same emp_id should go to duplicates list."""
        records = [
            {"emp_id": "101", "name": "Alice"},
            {"emp_id": "102", "name": "Bob"},
            {"emp_id": "101", "name": "Alice Duplicate"},  # ← duplicate
        ]
        valid, dupes = check_duplicates(records)
        assert len(valid) == 2      # only Alice (first) and Bob
        assert len(dupes) == 1      # only the second Alice
        dup_record, reason = dupes[0]
        assert dup_record["name"] == "Alice Duplicate"
        assert "Duplicate" in reason

    def test_first_occurrence_kept_not_second(self):
        """Make sure it's the FIRST occurrence that is kept."""
        records = [
            {"emp_id": "101", "name": "First Alice"},
            {"emp_id": "101", "name": "Second Alice"},  # ← should be rejected
        ]
        valid, dupes = check_duplicates(records)
        assert valid[0]["name"] == "First Alice"
        assert dupes[0][0]["name"] == "Second Alice"

    def test_empty_list_returns_empty(self):
        """Empty input → empty output, no crash."""
        valid, dupes = check_duplicates([])
        assert valid == []
        assert dupes == []

    def test_three_occurrences_of_same_id(self):
        """Three records with the same emp_id → 1 valid, 2 duplicates."""
        records = [
            {"emp_id": "101", "name": "A"},
            {"emp_id": "101", "name": "B"},
            {"emp_id": "101", "name": "C"},
        ]
        valid, dupes = check_duplicates(records)
        assert len(valid) == 1
        assert len(dupes) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Tests for transform_record()
# ─────────────────────────────────────────────────────────────────────────────

class TestTransformRecord:
    """Tests for the data transformation function."""

    def test_emp_id_converted_to_int(self, valid_record):
        """emp_id comes in as a string, must go out as an int."""
        result = transform_record(valid_record)
        assert isinstance(result["emp_id"], int)
        assert result["emp_id"] == 101

    def test_salary_converted_to_float(self, valid_record):
        """salary comes in as a string, must go out as a float."""
        result = transform_record(valid_record)
        assert isinstance(result["salary"], float)
        assert result["salary"] == 75000.0

    def test_country_uppercased(self, valid_record):
        """country should always be uppercase regardless of input case."""
        valid_record["country"] = "india"
        result = transform_record(valid_record)
        assert result["country"] == "INDIA"

    def test_country_mixed_case_uppercased(self, valid_record):
        """Mixed case country is also uppercased."""
        valid_record["country"] = "uNiTeD kInGdOm"
        result = transform_record(valid_record)
        assert result["country"] == "UNITED KINGDOM"

    def test_name_whitespace_trimmed(self, valid_record):
        """Leading/trailing spaces in name are stripped."""
        valid_record["name"] = "  Alice Johnson  "
        result = transform_record(valid_record)
        assert result["name"] == "Alice Johnson"

    def test_all_fields_present_in_output(self, valid_record):
        """The output dict must contain all 6 required fields."""
        result = transform_record(valid_record)
        for field in ["emp_id", "name", "doj", "country", "salary", "bank_account"]:
            assert field in result

    def test_bank_account_trimmed(self, valid_record):
        """Bank account leading/trailing spaces are stripped."""
        valid_record["bank_account"] = "  ACC1001  "
        result = transform_record(valid_record)
        assert result["bank_account"] == "ACC1001"

    def test_doj_converted_to_iso_format(self, valid_record):
        """DD-MM-YYYY format from Excel is converted to YYYY-MM-DD."""
        valid_record["doj"] = "15-03-2022"
        result = transform_record(valid_record)
        assert result["doj"] == "2022-03-15"
