"""Unit tests for the committed case-tag file and its loader
(app/eval/corpus.py::load_case_tags).

The committed CSV decides which clients ever see which case study, so it
gets the same cheapest-possible regression check the manifest gets: the real
file must load, and every token in it must be in the controlled vocabulary.
"""
from __future__ import annotations

import pytest

from app.eval.corpus import (
    DEFAULT_CASE_TAGS_PATH,
    CaseTagEntry,
    load_case_tags,
    load_manifest,
    tag_coverage,
    write_case_tags,
)
from app.services import case_taxonomy

MANIFEST_PATH = DEFAULT_CASE_TAGS_PATH.with_name("corpus_manifest.csv")


def _write(tmp_path, rows: list[str]):
    path = tmp_path / "case_tags.csv"
    path.write_text(
        "filename,tag_type,tag_value,confidence,note\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return path


class TestCommittedFile:
    def test_committed_case_tags_load(self):
        entries = load_case_tags(DEFAULT_CASE_TAGS_PATH)
        assert entries, "case_tags.csv is empty — the weights have nothing to bite on"

    def test_every_tag_is_in_the_controlled_vocabulary(self):
        # load_case_tags validates on read, so reaching here is the assertion;
        # this spells out why, because a typo'd tag never matches anything and
        # would make a case look unrelated to every client, forever.
        for e in load_case_tags(DEFAULT_CASE_TAGS_PATH):
            assert case_taxonomy.is_valid(e.tag_type, e.tag_value)

    def test_every_tagged_filename_is_in_the_manifest(self):
        manifest = load_manifest(MANIFEST_PATH)
        assert manifest, "corpus_manifest.csv is missing"
        for e in load_case_tags(DEFAULT_CASE_TAGS_PATH):
            assert e.filename in manifest, f"{e.filename} is tagged but not in the corpus"

    def test_every_case_has_an_industry_tag(self):
        # industry carries the joint-heaviest weight (0.25) and is the one
        # dimension derivable by rule from the manifest, so there is no excuse
        # for a case to be missing it.
        manifest = load_manifest(MANIFEST_PATH)
        tagged = {e.filename for e in load_case_tags(DEFAULT_CASE_TAGS_PATH) if e.tag_type == "industry"}
        assert set(manifest) <= tagged, f"untagged industry: {sorted(set(manifest) - tagged)}"

    def test_coverage_report_names_every_case(self):
        manifest = load_manifest(MANIFEST_PATH)
        coverage = tag_coverage(manifest, load_case_tags(DEFAULT_CASE_TAGS_PATH))
        assert set(coverage) == set(manifest)
        # Narrative dimensions are a known gap awaiting human review — this
        # asserts the report SAYS so rather than asserting they are done.
        assert all("industry" not in missing for missing in coverage.values())


class TestLoaderValidation:
    def test_unknown_tag_value_raises(self, tmp_path):
        path = _write(tmp_path, ["a.md,industry,beuaty,1.0,"])
        with pytest.raises(ValueError, match="controlled vocabulary"):
            load_case_tags(path)

    def test_unknown_dimension_raises(self, tmp_path):
        path = _write(tmp_path, ["a.md,budget,under_300k,1.0,"])
        with pytest.raises(ValueError, match="unknown tag dimension"):
            load_case_tags(path)

    def test_duplicate_row_raises(self, tmp_path):
        path = _write(tmp_path, ["a.md,industry,beauty,1.0,", "a.md,industry,beauty,1.0,"])
        with pytest.raises(ValueError, match="duplicate"):
            load_case_tags(path)

    def test_missing_required_column_value_raises(self, tmp_path):
        path = _write(tmp_path, ["a.md,,beauty,1.0,"])
        with pytest.raises(ValueError, match="required"):
            load_case_tags(path)

    @pytest.mark.parametrize("bad", ["0", "0.0", "1.5", "-0.2"])
    def test_confidence_outside_zero_to_one_raises(self, tmp_path, bad):
        path = _write(tmp_path, [f"a.md,industry,beauty,{bad},"])
        with pytest.raises(ValueError, match="confidence"):
            load_case_tags(path)

    def test_blank_confidence_defaults_to_one(self, tmp_path):
        path = _write(tmp_path, ["a.md,industry,beauty,,"])
        assert load_case_tags(path)[0].confidence == 1.0

    def test_several_tags_per_dimension_are_allowed(self, tmp_path):
        # A campaign can serve two audiences — this is why case_study_tags is
        # many-to-many and why the uniqueness key includes tag_value.
        path = _write(tmp_path, [
            "a.md,audience,gen_z_student,1.0,",
            "a.md,audience,working_adult,0.6,",
        ])
        assert len(load_case_tags(path)) == 2

    def test_missing_file_is_empty_not_an_error(self, tmp_path):
        assert load_case_tags(tmp_path / "nope.csv") == []

    def test_round_trip(self, tmp_path):
        entries = [
            CaseTagEntry("b.md", "objective", "awareness", 0.6, "proposed"),
            CaseTagEntry("a.md", "industry", "beauty", 1.0, None),
        ]
        path = tmp_path / "out.csv"
        write_case_tags(path, entries)
        back = load_case_tags(path)
        assert [e.filename for e in back] == ["a.md", "b.md"]  # sorted on write
        assert back[1].confidence == 0.6
        assert back[1].note == "proposed"
