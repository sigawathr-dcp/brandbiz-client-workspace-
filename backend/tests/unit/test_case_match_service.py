"""Unit tests for app/services/case_match.py — the retrieval pipeline
extracted out of POST /client/cases so production and the offline eval
harness (backend/scripts/eval_case_match_*.py) share one implementation.

Pure-function coverage only (collapse_best_per_file, to_match_score,
build_context_query); match_cases() itself touches the DB and is exercised
by the integration suite / the eval harness script, not here.
"""
from __future__ import annotations

from app.services.case_match import (
    build_context_query,
    collapse_best_per_file,
    to_match_score,
)
from app.services.client_intake import FIELD_LABELS, INTAKE_SCRIPT
from app.tools.rag_search import RetrievedChunk


def _chunk(file_id: str, filename: str, chunk_index: int, distance: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"{file_id}:{chunk_index}",
        file_id=file_id,
        filename=filename,
        chunk_index=chunk_index,
        content=f"content of {filename} chunk {chunk_index}",
        score=distance,  # RetrievedChunk.score is cosine distance
        scope="org",
    )


class TestCollapseBestPerFile:
    def test_keeps_lowest_distance_chunk_per_file(self):
        file_a = "11111111-1111-1111-1111-111111111111"
        file_b = "22222222-2222-2222-2222-222222222222"
        chunks = [
            _chunk(file_a, "a.md", 0, 0.42),
            _chunk(file_a, "a.md", 1, 0.31),  # closer — should win for file A
            _chunk(file_b, "b.md", 0, 0.35),
        ]

        result = collapse_best_per_file(chunks)

        by_file = {c.file_id: c for c in result}
        assert len(result) == 2
        assert by_file[file_a].score == 0.31
        assert by_file[file_a].chunk_index == 1
        assert by_file[file_b].score == 0.35

    def test_empty_input_returns_empty(self):
        assert collapse_best_per_file([]) == []


class TestToMatchScore:
    def test_typical_distance(self):
        assert to_match_score(0.3) == 0.7

    def test_clamped_below_zero(self):
        # cosine distance can exceed 1.0; 1 - distance must not go negative
        assert to_match_score(1.4) == 0.0

    def test_clamped_above_one(self):
        assert to_match_score(-0.2) == 1.0

    def test_zero_distance_is_perfect_score(self):
        assert to_match_score(0.0) == 1.0


class TestBuildContextQuery:
    def test_canonical_order_matches_intake_script(self):
        # Fields supplied out of order must still be flattened in
        # INTAKE_SCRIPT order — production always writes them in order
        # (intake is answered sequentially), but a caller building `fields`
        # some other way (e.g. the eval harness's golden profiles) must not
        # get a nondeterministic query.
        fields = {
            "budget": "Under ฿300,000",
            "industry": "Food & beverage / café",
            "history": "None",
        }

        query = build_context_query(fields)

        industry_pos = query.index("Business:")
        budget_pos = query.index("Budget band:")
        history_pos = query.index("Brand history:")
        assert industry_pos < budget_pos < history_pos

    def test_exact_string_shape(self):
        fields = {"industry": "Food & beverage / café", "stage": "Growing, ready to expand"}

        query = build_context_query(fields)

        assert query == (
            f"{FIELD_LABELS['industry']}: Food & beverage / café; "
            f"{FIELD_LABELS['stage']}: Growing, ready to expand"
        )

    def test_missing_fields_are_skipped_not_errored(self):
        # A partial profile (e.g. intake abandoned mid-way) must not raise.
        fields = {"industry": "Retail + online"}

        query = build_context_query(fields)

        assert query == f"{FIELD_LABELS['industry']}: Retail + online"

    def test_covers_every_intake_script_field(self):
        # FIELD_LABELS and INTAKE_SCRIPT must stay in sync — a field present
        # in the script but missing a label would silently fall back to its
        # raw key (see build_context_query's .get(k, k)), which is a corpus
        # authoring bug, not a valid state.
        script_fields = {step["field"] for step in INTAKE_SCRIPT}
        assert script_fields <= set(FIELD_LABELS)
