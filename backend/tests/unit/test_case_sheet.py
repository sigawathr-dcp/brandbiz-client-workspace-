"""Unit tests for reading the curated case-study spreadsheet.

These run against the committed workbook (backend/data/case_studies_dsme.xlsx),
not a fixture, because the risks being defended against are properties of
THAT file: that its layout is what the positional column map assumes, that
its known errata still bite, and that every row still resolves to exactly
one corpus file. A fixture would pass while the real build broke.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.eval import case_sheet, case_tag_map

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SHEET = BACKEND_ROOT / "data" / "case_studies_dsme.xlsx"
CORPUS_DIR = BACKEND_ROOT / "data" / "case_studies"

pytestmark = pytest.mark.skipif(
    not SHEET.exists(), reason="curated case-study workbook not present"
)


@pytest.fixture(scope="module")
def cases() -> list[case_sheet.SheetCase]:
    return case_sheet.load_cases(SHEET)


@pytest.fixture(scope="module")
def corrected(cases) -> list[case_sheet.SheetCase]:
    fixed, _applied, _stale = case_sheet.apply_errata(list(cases))
    return fixed


class TestSheetShape:
    def test_reads_every_curated_case(self, cases):
        assert len(cases) == 22

    def test_footnote_rows_are_not_cases(self, cases):
        # Four trailing rows carry only column A — the sheet author's notes
        # to the AI, not data. Every case must have a title and a client.
        for c in cases:
            assert c.title and c.client, c

    def test_a_restructured_sheet_fails_loudly(self, tmp_path):
        # The column map is positional; silently reading the wrong column
        # would mis-tag the whole corpus.
        with pytest.raises(ValueError, match="no sheet named"):
            case_sheet.load_cases(SHEET, sheet_name="Not A Real Sheet")

    def test_own_commerce_is_not_a_tag_dimension(self, cases):
        assert "own_commerce" not in case_sheet.TAG_DIMENSIONS
        # ...and the sheet leaves that column empty on every row, which is
        # what makes it a solution trigger rather than a corpus tag.
        rows = case_sheet.read_sheet(SHEET, "Case study")
        col = case_sheet.COL["own_commerce"]
        values = [r[col] for r in rows[1:] if len(r) > col and r[col]]
        assert values == []

    def test_feasibility_columns_are_not_tag_dimensions(self, cases):
        assert "timeframe" not in case_sheet.TAG_DIMENSIONS
        assert "budget" not in case_sheet.TAG_DIMENSIONS


class TestErrata:
    def test_both_errata_still_apply(self, cases):
        _fixed, applied, stale = case_sheet.apply_errata(list(cases))
        assert {e.case_no for e in applied} == {"0", "1"}
        assert stale == [], stale

    def test_duplicate_row_is_dropped(self, corrected):
        assert len(corrected) == 21
        assert "0" not in {c.case_no for c in corrected}

    def test_transplanted_url_points_at_the_right_campaign(self, corrected):
        case_1 = next(c for c in corrected if c.case_no == "1")
        assert case_1.source_slug == "grabfood__mega_sale"

    def test_the_donor_row_is_untouched(self, corrected):
        # Case #6 is AURA BLUE and keeps the URL case #1 wrongly held.
        case_6 = next(c for c in corrected if c.case_no == "6")
        assert case_6.source_slug == "aura_blue_x_bar_b_gon"

    def test_errata_are_reported_stale_rather_than_reapplied(self, cases):
        # If a future revision fixes case #1 at source, re-pointing the URL
        # would undo that fix. Simulate the fixed sheet.
        from dataclasses import replace

        fixed_at_source = [
            replace(c, source="https://example.invalid/whatever") if c.case_no == "1" else c
            for c in cases
        ]
        _out, applied, stale = case_sheet.apply_errata(fixed_at_source)
        assert "1" not in {e.case_no for e in applied}
        assert any(s.startswith("A:") for s in stale)


class TestResolution:
    @pytest.fixture(scope="class")
    def resolution(self):
        cases, _, _ = case_sheet.apply_errata(case_sheet.load_cases(SHEET))
        return case_sheet.resolve_filenames(cases, case_sheet.scan_corpus_dir(CORPUS_DIR))

    def test_no_two_rows_claim_one_file(self, resolution):
        # A collision means one case study would be overwritten with another
        # campaign's content and tags.
        assert resolution.collisions == {}

    def test_every_row_resolves(self, resolution):
        # After the corpus rebuild there are no unplaced rows left: the one
        # genuinely new case (CASETiFY) now has a file of its own.
        assert [c.title for c in resolution.unresolved] == []

    def test_the_corpus_is_exactly_the_sheet(self, resolution):
        # The corpus was cut back to the sheet's 21 rows: six scraped-only
        # cases (aura_me, grab_x_disney, grabmart, grabmart_2, ppg_x_grab,
        # siam_orchard) carried no row, so they could only ever be tagged on
        # `industry` and scored blind on the other five dimensions. A file
        # with no row is now a build error rather than a permanent gap.
        assert resolution.unclaimed == []

    def test_title_drift_does_not_break_identity(self, resolution):
        # "BENOVA GOBAL" in the sheet vs. the campaign title on disk; the
        # portfolio URL is what actually joins them.
        assert resolution.by_case_no["17"] == "case-study_benova_rejuvenus.md"
        assert resolution.how["17"] == "source slug"


class TestEveryCellResolves:
    """The build refuses to write tags while any phrase is unmapped, so this
    is the test that keeps the committed workbook buildable."""

    def test_every_tag_cell_maps_to_at_least_one_token(self, corrected):
        problems = []
        for case in corrected:
            for dimension in case_sheet.TAG_DIMENSIONS:
                raw = case.tags.get(dimension, "")
                if not raw:
                    problems.append(f"#{case.case_no} {dimension}: blank")
                    continue
                try:
                    tokens = case_tag_map.tags_for(dimension, raw)
                except ValueError as exc:
                    problems.append(f"#{case.case_no} {exc}")
                    continue
                if not tokens:
                    problems.append(f"#{case.case_no} {dimension}: {raw!r} -> no tokens")
        assert problems == [], "\n".join(problems)
