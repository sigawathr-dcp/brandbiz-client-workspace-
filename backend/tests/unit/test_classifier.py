"""Unit tests for app.services.classifier (Task 2.1).

Strategy
--------
All tests operate on the *pure* ``_compile_rules`` helper — no DB, no SQLAlchemy
session required.  Each test fixture populates the module-level ``_RULES`` cache
directly and tears it down via the ``loaded_rules`` autouse fixture so tests are
independent.

Seeded rules mirror the 5 patterns from 0001_baseline (all TIER_3_CONFIDENTIAL).
The keyword rule "Project Apollo" (TIER_4_RESTRICTED) is added only in tests that
exercise TIER_4 behaviour — it is not in the DB seed (test-only, per acceptance
criteria).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import app.services.classifier as classifier_module
from app.models.classification import DataTier
from app.services.classifier import (
    _compile_rules,
    detect_tier,
    is_valid_thai_national_id,
)


# ---------------------------------------------------------------------------
# Helpers — build fake ORM rows without touching SQLAlchemy
# ---------------------------------------------------------------------------

def _row(
    name: str,
    pattern_type: str,
    pattern: str,
    detected_tier: str,
) -> Any:
    """Return a SimpleNamespace that quacks like a DataClassificationRule row."""
    return SimpleNamespace(
        name=name,
        pattern_type=pattern_type,
        pattern=pattern,
        detected_tier=detected_tier,
    )


# ---------------------------------------------------------------------------
# Baseline 5 seeded regex rules (all TIER_3_CONFIDENTIAL)
# ---------------------------------------------------------------------------

_SEEDED_ROWS = [
    _row("Thai National ID",          "regex", r"\d-\d{4}-\d{5}-\d{2}-\d", "TIER_3_CONFIDENTIAL"),
    _row("Thai National ID (compact)", "regex", r"\d{13}",                   "TIER_3_CONFIDENTIAL"),
    _row("Thai Mobile",               "regex", r"0[689]\d{8}",               "TIER_3_CONFIDENTIAL"),
    _row("Email",                     "regex", r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "TIER_3_CONFIDENTIAL"),
    _row("Bank Account TH",           "regex", r"\d{3}-\d-\d{5}-\d",        "TIER_3_CONFIDENTIAL"),
    _row("Credit Card",               "regex", r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}", "TIER_3_CONFIDENTIAL"),
]

_KEYWORD_APOLLO = _row("Project Apollo", "keyword", "Project Apollo", "TIER_4_RESTRICTED")


# ---------------------------------------------------------------------------
# Fixture: load the cache before each test, restore empty afterwards
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def loaded_rules():
    """Populate _RULES with the 5 seeded rows + Apollo keyword, reset after each test."""
    all_rows = _SEEDED_ROWS + [_KEYWORD_APOLLO]
    classifier_module._RULES = _compile_rules(all_rows)
    yield
    classifier_module._RULES = []


# ---------------------------------------------------------------------------
# Thai National-ID Mod-11 checksum — isolated tests
# ---------------------------------------------------------------------------

class TestThaiNationalIDChecksum:
    def test_valid_checksum_returns_true(self):
        # 1-2345-67890-12-1: weighted sum = 352, 352%11=0, (11-0)%10=1 ✓
        assert is_valid_thai_national_id("1-2345-67890-12-1") is True

    def test_valid_checksum_with_prefix_text(self):
        assert is_valid_thai_national_id("บัตรประชาชน 1-2345-67890-12-1") is True

    def test_invalid_checksum_returns_false(self):
        # Last digit changed to 9, check digit should be 1
        assert is_valid_thai_national_id("1-2345-67890-12-9") is False

    def test_too_few_digits_returns_false(self):
        assert is_valid_thai_national_id("1234567890") is False

    def test_too_many_digits_returns_false(self):
        assert is_valid_thai_national_id("12345678901234") is False

    def test_no_digits_returns_false(self):
        assert is_valid_thai_national_id("no digits here") is False


# ---------------------------------------------------------------------------
# detect_tier — one test per seeded pattern
# ---------------------------------------------------------------------------

class TestSeededPatterns:
    def test_thai_national_id_valid_checksum(self):
        """Valid Thai ID → TIER_3."""
        assert detect_tier("My ID is 1-2345-67890-12-1") == DataTier.TIER_3_CONFIDENTIAL

    def test_thai_national_id_invalid_checksum_not_flagged(self):
        """Invalid checksum must NOT be flagged — falls back to TIER_1."""
        assert detect_tier("1-2345-67890-12-9") == DataTier.TIER_1_PUBLIC

    def test_thai_national_id_with_thai_text_valid(self):
        """Positive: acceptance-criteria case with Thai prefix."""
        assert detect_tier("บัตรประชาชน 1-2345-67890-12-1") == DataTier.TIER_3_CONFIDENTIAL

    def test_thai_national_id_compact_valid(self):
        """Dash-less 13-digit Thai ID with valid checksum → TIER_3 (0004_thai_id_compact rule).

        1234567890121 is the compact (no-dash) form of 1-2345-67890-12-1, which is
        already used in the dashed-rule tests.  Both checksums are verified.
        """
        assert detect_tier("My ID is 1234567890121") == DataTier.TIER_3_CONFIDENTIAL

    def test_thai_national_id_compact_invalid_checksum_not_flagged(self):
        """13 digits with bad Mod-11 checksum must NOT be flagged — validator rejects it.

        1234567890129 — same prefix, last digit changed from 1 to 9 (invalid checksum).
        Also covers the real-world case: the tester input 1195644567342 has expected
        check digit 3 but ends in 2 — it would correctly stay TIER_1.
        """
        assert detect_tier("1234567890129") == DataTier.TIER_1_PUBLIC
        assert detect_tier("1195644567342") == DataTier.TIER_1_PUBLIC  # invalid checksum

    def test_thai_national_id_compact_no_dashes_in_sentence(self):
        """Compact ID embedded in Thai text → TIER_3."""
        assert detect_tier("บัตรประชาชนเลขที่ 1234567890121 ครับ") == DataTier.TIER_3_CONFIDENTIAL

    def test_thai_mobile(self):
        assert detect_tier("Call me at 0891234567") == DataTier.TIER_3_CONFIDENTIAL

    def test_email(self):
        assert detect_tier("Contact: alice@example.com") == DataTier.TIER_3_CONFIDENTIAL

    def test_bank_account(self):
        assert detect_tier("Transfer to 123-4-56789-0") == DataTier.TIER_3_CONFIDENTIAL

    def test_credit_card_spaced(self):
        assert detect_tier("Card: 4111 1111 1111 1111") == DataTier.TIER_3_CONFIDENTIAL

    def test_credit_card_dashed(self):
        assert detect_tier("4111-1111-1111-1111") == DataTier.TIER_3_CONFIDENTIAL

    def test_credit_card_no_separator(self):
        assert detect_tier("4111111111111111") == DataTier.TIER_3_CONFIDENTIAL


# ---------------------------------------------------------------------------
# detect_tier — keyword rule (TIER_4)
# ---------------------------------------------------------------------------

class TestKeywordRule:
    def test_project_apollo_keyword(self):
        """Acceptance-criteria keyword rule → TIER_4."""
        assert detect_tier("Project Apollo M&A target list") == DataTier.TIER_4_RESTRICTED

    def test_project_apollo_case_insensitive(self):
        assert detect_tier("project apollo target") == DataTier.TIER_4_RESTRICTED

    def test_project_apollo_in_longer_text(self):
        assert detect_tier("Hello! Re: Project Apollo deal — see attached.") == DataTier.TIER_4_RESTRICTED


# ---------------------------------------------------------------------------
# detect_tier — edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_string_returns_tier_1(self):
        assert detect_tier("") == DataTier.TIER_1_PUBLIC

    def test_whitespace_only_returns_tier_1(self):
        assert detect_tier("   \t\n  ") == DataTier.TIER_1_PUBLIC

    def test_safe_text_returns_tier_1(self):
        assert detect_tier("Hello, how are you?") == DataTier.TIER_1_PUBLIC

    def test_multiple_matches_highest_tier_wins(self):
        """Email (TIER_3) + Project Apollo keyword (TIER_4) → TIER_4."""
        text = "alice@example.com — Project Apollo M&A update"
        assert detect_tier(text) == DataTier.TIER_4_RESTRICTED

    def test_full_history_payload(self):
        """§7.6: classifier runs on full conversation history + new message."""
        history = "User: Hello\nAssistant: Hi there\n"
        new_msg = "User: My ID is 1-2345-67890-12-1, please help."
        assert detect_tier(history + new_msg) == DataTier.TIER_3_CONFIDENTIAL


# ---------------------------------------------------------------------------
# Compile-rules helpers — NER and unknown types are silently skipped
# ---------------------------------------------------------------------------

class TestCompileRules:
    def test_ner_rule_is_skipped(self):
        rows = [_row("NER Test", "ner", "PERSON", "TIER_3_CONFIDENTIAL")]
        rules = _compile_rules(rows)
        assert rules == []

    def test_unknown_type_is_skipped(self):
        rows = [_row("Unknown", "ml_model", "some-model", "TIER_2_INTERNAL")]
        rules = _compile_rules(rows)
        assert rules == []

    def test_invalid_regex_is_skipped(self):
        rows = [_row("Bad Regex", "regex", r"[[[", "TIER_3_CONFIDENTIAL")]
        rules = _compile_rules(rows)
        assert rules == []

    def test_compile_seeded_rows_count(self):
        # 6 seeded rows: Thai National ID, Thai National ID (compact), Thai Mobile,
        # Email, Bank Account TH, Credit Card
        rules = _compile_rules(_SEEDED_ROWS)
        assert len(rules) == 6

    def test_compile_keyword_row(self):
        rules = _compile_rules([_KEYWORD_APOLLO])
        assert len(rules) == 1
        assert rules[0].kind == "keyword"
        assert rules[0].tier == DataTier.TIER_4_RESTRICTED
