"""Unit tests for app/eval/goldens.py — profile/label loading and
validation for the case-match eval harness."""
from __future__ import annotations

import json

import pytest

from app.eval.goldens import (
    DEFAULT_PROFILES_PATH,
    load_labels,
    load_profiles,
    profile_thai_summary,
    thai_chip_label,
)
from app.services.client_intake import INTAKE_SCRIPT

# Derived from the script rather than transcribed from it: this fixture went
# stale the moment intake v2 renamed goal -> objective and horizon ->
# timeframe, and a hand-written copy would go stale again on v3. First chip
# of each question is an arbitrary but stable choice.
_VALID_FIELDS = {
    step["field"]: step["options"][0]["value"] for step in INTAKE_SCRIPT
}
_FIRST_INDUSTRY = _VALID_FIELDS["industry"]
_FIRST_INDUSTRY_TH = INTAKE_SCRIPT[0]["options"][0]["label"]
_LAST_FIELD = INTAKE_SCRIPT[-1]["field"]


def _write_profiles(tmp_path, profiles: list[dict]):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"version": 1, "note": "", "profiles": profiles}), encoding="utf-8")
    return path


class TestLoadProfilesCommittedFile:
    """The real committed golden set must itself be valid — this is the
    cheapest possible regression check against a hand-edit typo."""

    def test_committed_profiles_json_is_valid(self):
        profiles = load_profiles(DEFAULT_PROFILES_PATH)
        assert len(profiles) == 18

    def test_committed_profiles_have_unique_ids(self):
        profiles = load_profiles(DEFAULT_PROFILES_PATH)
        ids = [p.id for p in profiles]
        assert len(ids) == len(set(ids))

    def test_committed_profiles_cover_every_industry_chip(self):
        profiles = load_profiles(DEFAULT_PROFILES_PATH)
        industry_values = {p.fields["industry"] for p in profiles if "industry" not in p.free_text_fields}
        chip_values = {opt["value"] for step in INTAKE_SCRIPT if step["field"] == "industry" for opt in step["options"]}
        assert chip_values <= industry_values


class TestLoadProfilesValidation:
    def test_valid_profile_loads(self, tmp_path):
        path = _write_profiles(tmp_path, [
            {"id": "X1", "label_th": "", "note": "", "free_text_fields": [], "fields": _VALID_FIELDS}
        ])
        profiles = load_profiles(path)
        assert profiles[0].id == "X1"
        assert profiles[0].fields["industry"] == _FIRST_INDUSTRY

    def test_invalid_chip_value_raises(self, tmp_path):
        bad_fields = dict(_VALID_FIELDS, industry="Not a real chip value")
        path = _write_profiles(tmp_path, [
            {"id": "X1", "label_th": "", "note": "", "free_text_fields": [], "fields": bad_fields}
        ])
        with pytest.raises(ValueError, match="not a valid chip value"):
            load_profiles(path)

    def test_free_text_field_skips_chip_validation(self, tmp_path):
        fields = dict(_VALID_FIELDS, industry="ร้านขายของออนไลน์ทั่วไป")
        path = _write_profiles(tmp_path, [
            {"id": "X1", "label_th": "", "note": "", "free_text_fields": ["industry"], "fields": fields}
        ])
        profiles = load_profiles(path)
        assert profiles[0].fields["industry"] == "ร้านขายของออนไลน์ทั่วไป"

    def test_empty_free_text_value_raises(self, tmp_path):
        fields = dict(_VALID_FIELDS, industry="   ")
        path = _write_profiles(tmp_path, [
            {"id": "X1", "label_th": "", "note": "", "free_text_fields": ["industry"], "fields": fields}
        ])
        with pytest.raises(ValueError, match="empty"):
            load_profiles(path)

    def test_missing_field_raises(self, tmp_path):
        fields = dict(_VALID_FIELDS)
        del fields[_LAST_FIELD]
        path = _write_profiles(tmp_path, [
            {"id": "X1", "label_th": "", "note": "", "free_text_fields": [], "fields": fields}
        ])
        with pytest.raises(ValueError, match="missing intake field"):
            load_profiles(path)

    def test_unknown_field_raises(self, tmp_path):
        fields = dict(_VALID_FIELDS, made_up_field="value")
        path = _write_profiles(tmp_path, [
            {"id": "X1", "label_th": "", "note": "", "free_text_fields": [], "fields": fields}
        ])
        with pytest.raises(ValueError, match="unknown intake field"):
            load_profiles(path)

    def test_duplicate_id_raises(self, tmp_path):
        path = _write_profiles(tmp_path, [
            {"id": "X1", "label_th": "", "note": "", "free_text_fields": [], "fields": _VALID_FIELDS},
            {"id": "X1", "label_th": "", "note": "", "free_text_fields": [], "fields": _VALID_FIELDS},
        ])
        with pytest.raises(ValueError, match="duplicate profile id"):
            load_profiles(path)

    def test_empty_profile_list_raises(self, tmp_path):
        path = _write_profiles(tmp_path, [])
        with pytest.raises(ValueError, match="no profiles found"):
            load_profiles(path)


class TestThaiChipLabel:
    def test_known_chip_value_reverse_maps(self):
        assert thai_chip_label("industry", _FIRST_INDUSTRY) == _FIRST_INDUSTRY_TH

    def test_unknown_value_returns_none(self):
        assert thai_chip_label("industry", "ร้านขายของออนไลน์ทั่วไป") is None


class TestProfileThaiSummary:
    def test_falls_back_to_raw_value_for_free_text(self, tmp_path):
        fields = dict(_VALID_FIELDS, industry="ร้านขายเครื่องสำอางออนไลน์")
        path = _write_profiles(tmp_path, [
            {"id": "X1", "label_th": "", "note": "", "free_text_fields": ["industry"], "fields": fields}
        ])
        profile = load_profiles(path)[0]
        summary = profile_thai_summary(profile)
        assert "ร้านขายเครื่องสำอางออนไลน์" in summary
        assert summary.startswith("ธุรกิจ:")

    def test_uses_thai_chip_label_when_available(self, tmp_path):
        path = _write_profiles(tmp_path, [
            {"id": "X1", "label_th": "", "note": "", "free_text_fields": [], "fields": _VALID_FIELDS}
        ])
        profile = load_profiles(path)[0]
        summary = profile_thai_summary(profile)
        assert _FIRST_INDUSTRY_TH in summary  # Thai label for the first industry chip


class TestLoadLabels:
    def _write_labels(self, tmp_path, rows: list[str], name: str = "labels.csv"):
        path = tmp_path / name
        header = "profile_id,filename,label,labeled_by,labeled_at,note\n"
        path.write_text(header + "\n".join(rows), encoding="utf-8")
        return path

    def test_basic_parse(self, tmp_path):
        path = self._write_labels(tmp_path, [
            "P01-cafe-expand,case-study_a.md,2,ploy,2026-08-12,ตรงมาก",
            "P01-cafe-expand,case-study_b.md,0,ploy,2026-08-12,",
        ])
        labels = load_labels(path)
        assert labels.label_for("P01-cafe-expand", "case-study_a.md") == 2
        assert labels.label_for("P01-cafe-expand", "case-study_b.md") == 0
        assert not labels.is_placeholder

    def test_missing_pair_defaults_to_zero(self, tmp_path):
        path = self._write_labels(tmp_path, [
            "P01-cafe-expand,case-study_a.md,2,ploy,2026-08-12,",
        ])
        labels = load_labels(path)
        assert labels.label_for("P01-cafe-expand", "case-study_never_judged.md") == 0

    def test_out_of_range_label_raises(self, tmp_path):
        path = self._write_labels(tmp_path, [
            "P01-cafe-expand,case-study_a.md,3,ploy,2026-08-12,",
        ])
        with pytest.raises(ValueError, match="not in"):
            load_labels(path)

    def test_duplicate_pair_raises(self, tmp_path):
        path = self._write_labels(tmp_path, [
            "P01-cafe-expand,case-study_a.md,2,ploy,2026-08-12,",
            "P01-cafe-expand,case-study_a.md,0,someone_else,2026-08-13,",
        ])
        with pytest.raises(ValueError, match="duplicate label"):
            load_labels(path)

    def test_placeholder_suffix_is_flagged(self, tmp_path):
        path = self._write_labels(
            tmp_path,
            ["P01-cafe-expand,case-study_a.md,2,bootstrap,2026-08-12,"],
            name="labels.placeholder.csv",
        )
        labels = load_labels(path)
        assert labels.is_placeholder

    def test_judged_filenames_for_profile(self, tmp_path):
        path = self._write_labels(tmp_path, [
            "P01-cafe-expand,case-study_a.md,2,ploy,2026-08-12,",
            "P01-cafe-expand,case-study_b.md,1,ploy,2026-08-12,",
            "P02-retail-online,case-study_a.md,0,ploy,2026-08-12,",
        ])
        labels = load_labels(path)
        assert labels.judged_filenames("P01-cafe-expand") == {"case-study_a.md", "case-study_b.md"}
