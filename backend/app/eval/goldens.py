"""
app/eval/goldens.py

Load and validate the case-match eval harness's golden set:
backend/eval/case_match/profiles.json (hand-authored synthetic client
personas — NEVER derived from real ClientProfile rows, which are encrypted
client PII) and backend/eval/case_match/labels.csv (consultant-assigned
relevance grades, produced by scripts/eval_case_match_import.py from a
filled-in labeling sheet).

Profile field values are validated against
app.services.client_intake.INTAKE_SCRIPT's chip values (unless the field is
listed in the profile's free_text_fields) — a typo'd value would otherwise
evaluate a query no real client could ever produce, and the failure would
be invisible in a report full of plausible-looking numbers.
"""
from __future__ import annotations

import csv
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.services.client_intake import INTAKE_SCRIPT, THAI_FIELD_LABELS

# backend/app/eval/goldens.py -> parents[2] == backend/
_BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_PROFILES_PATH = _BACKEND_DIR / "eval" / "case_match" / "profiles.json"
DEFAULT_LABELS_PATH = _BACKEND_DIR / "eval" / "case_match" / "labels.csv"

# THAI_FIELD_LABELS now lives in client_intake next to FIELD_LABELS (the
# market-scan prompt reads it too, so the labeling sheet and the prompt can't
# drift apart). Imported above and used by profile_thai_summary(); still
# importable from this module, which is where query_variants.py reads it.

_VALID_LABELS = {0, 1, 2}


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldenProfile:
    id: str
    label_th: str
    note: str
    free_text_fields: frozenset[str]
    fields: Mapping[str, str]


def _chip_values_by_field() -> dict[str, set[str]]:
    return {
        step["field"]: {opt["value"] for opt in step["options"]}
        for step in INTAKE_SCRIPT
    }


def _chip_label_by_value(field_key: str) -> dict[str, str]:
    for step in INTAKE_SCRIPT:
        if step["field"] == field_key:
            return {opt["value"]: opt["label"] for opt in step["options"]}
    return {}


def _script_fields() -> list[str]:
    return [step["field"] for step in INTAKE_SCRIPT]


def load_profiles(path: Path | str = DEFAULT_PROFILES_PATH) -> list[GoldenProfile]:
    """Load and validate every profile in profiles.json.

    Raises ValueError (not a silent skip) on: a missing INTAKE_SCRIPT
    field, an unknown field key, or a value that doesn't match any chip
    for that field and isn't declared free-text. Golden profiles that
    can't be produced by the real intake flow would make every metric
    downstream measure a fiction.
    """
    import json

    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    chip_values = _chip_values_by_field()
    script_fields = set(_script_fields())

    profiles: list[GoldenProfile] = []
    seen_ids: set[str] = set()
    for entry in raw.get("profiles", []):
        pid = entry["id"]
        if pid in seen_ids:
            raise ValueError(f"profiles.json: duplicate profile id {pid!r}")
        seen_ids.add(pid)

        fields = entry["fields"]
        free_text_fields = frozenset(entry.get("free_text_fields", []))

        unknown_keys = set(fields) - script_fields
        if unknown_keys:
            raise ValueError(f"{pid}: unknown intake field(s) {sorted(unknown_keys)}")
        missing_keys = script_fields - set(fields)
        if missing_keys:
            raise ValueError(f"{pid}: missing intake field(s) {sorted(missing_keys)}")

        bad_free_text = free_text_fields - script_fields
        if bad_free_text:
            raise ValueError(f"{pid}: free_text_fields references unknown field(s) {sorted(bad_free_text)}")

        for f, value in fields.items():
            if f in free_text_fields:
                if not value or not value.strip():
                    raise ValueError(f"{pid}: free-text field {f!r} is empty")
                continue
            if value not in chip_values[f]:
                raise ValueError(
                    f"{pid}: {f!r}={value!r} is not a valid chip value for that field "
                    f"(and {f!r} is not listed in free_text_fields). "
                    f"Valid values: {sorted(chip_values[f])}"
                )

        profiles.append(
            GoldenProfile(
                id=pid,
                label_th=entry.get("label_th", ""),
                note=entry.get("note", ""),
                free_text_fields=free_text_fields,
                fields=fields,
            )
        )

    if not profiles:
        raise ValueError(f"{path}: no profiles found")
    return profiles


def thai_chip_label(field_key: str, value: str) -> str | None:
    """Reverse-map a stored English chip value back to its Thai chip label
    (for the labeling sheet's profile summary column). Returns None for a
    free-text value or any value that doesn't match a known chip — the
    caller falls back to the raw value in that case."""
    return _chip_label_by_value(field_key).get(value)


def profile_thai_summary(profile: GoldenProfile) -> str:
    """'ธุรกิจ: ... | ระยะ: ... | ...' — the profile column shown to a
    consultant on the labeling sheet, entirely in Thai (falling back to the
    raw stored value for free-text fields, which are typically already
    Thai prose)."""
    parts = []
    for f in _script_fields():
        value = profile.fields[f]
        display = thai_chip_label(f, value) or value
        parts.append(f"{THAI_FIELD_LABELS.get(f, f)}: {display}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LabelRow:
    profile_id: str
    filename: str
    label: int
    labeled_by: str
    labeled_at: str
    note: str


@dataclass(frozen=True)
class GoldenLabels:
    rows: dict[tuple[str, str], LabelRow]
    is_placeholder: bool

    def label_for(self, profile_id: str, filename: str) -> int:
        """The judged label for (profile_id, filename), defaulting to 0
        (irrelevant) when no consultant has judged that pair yet — an
        unjudged pair is not "unknown", it's "not shown to be relevant"."""
        row = self.rows.get((profile_id, filename))
        return row.label if row is not None else 0

    def judged_filenames(self, profile_id: str) -> set[str]:
        return {fn for (pid, fn) in self.rows if pid == profile_id}


def load_labels(path: Path | str = DEFAULT_LABELS_PATH) -> GoldenLabels:
    """Parse a labels CSV (profile_id,filename,label,labeled_by,labeled_at,note).

    Raises ValueError on: an out-of-range label, or a duplicate
    (profile_id, filename) pair — either indicates the sheet was hand-
    edited inconsistently and must be fixed before the harness can trust
    it. A filename matching *.placeholder.csv is flagged (is_placeholder)
    rather than rejected — the export script's --bootstrap-labels output
    is meant to unblock the harness's own plumbing tests before any human
    has labeled anything, and its metrics are meaningless by construction.
    """
    path = Path(path)
    rows: dict[tuple[str, str], LabelRow] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, raw in enumerate(reader, start=2):  # header is row 1
            try:
                label = int(raw["label"])
            except (KeyError, ValueError) as exc:
                raise ValueError(f"{path}:{i}: label must be an integer, got {raw.get('label')!r}") from exc
            if label not in _VALID_LABELS:
                raise ValueError(f"{path}:{i}: label {label} not in {sorted(_VALID_LABELS)}")

            key = (raw["profile_id"], raw["filename"])
            if key in rows:
                raise ValueError(f"{path}:{i}: duplicate label for {key}")

            rows[key] = LabelRow(
                profile_id=raw["profile_id"],
                filename=raw["filename"],
                label=label,
                labeled_by=raw.get("labeled_by", ""),
                labeled_at=raw.get("labeled_at", ""),
                note=raw.get("note", ""),
            )

    return GoldenLabels(rows=rows, is_placeholder=path.name.endswith(".placeholder.csv"))
