"""
backend/scripts/eval_case_match_import.py

Step 2 of the case-match eval harness's human-labeling loop: takes a
labeling_sheet.csv a Brandbiz consultant filled in (see
scripts/eval_case_match_export.py + LABELING.th.md) and turns it into the
canonical, committed backend/eval/case_match/labels.csv — dropping the
presentation-only columns, validating every row, and sorting canonically
so future label revisions produce small, reviewable diffs.

Needs no database and no running backend — only the filled sheet, the
committed corpus_manifest.csv (for known filenames), and profiles.json
(for known profile ids). Runs anywhere Python + the repo are available;
the container is not required (unlike the export/run scripts, which need
live retrieval).

A blank relevance cell is treated as an explicit 0 (see LABELING.th.md:
"a blank cell means 0") and is written to labels.csv like any other judged
row — the consultant saw that row, decided it wasn't relevant, and that is
a real judgement, not a missing one.

Idempotent: re-importing the same filled sheet produces a byte-identical
labels.csv.

Usage:
    python scripts/eval_case_match_import.py \\
        --in eval/case_match/out/labeling_sheet_filled.csv \\
        --out eval/case_match/labels.csv \\
        --labeled-by ploy --labeled-at 2026-08-12
"""
import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.eval import corpus as corpus_mod
from app.eval import goldens

_VALID_LABELS = {"", "0", "1", "2"}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--in", dest="in_path", required=True, help="filled-in labeling sheet CSV")
    p.add_argument("--out", required=True, help="path to write the canonical labels.csv")
    p.add_argument("--labeled-by", required=True, help="first name only — see PLAN.md, no contact PII in git")
    p.add_argument("--labeled-at", default=None, help="YYYY-MM-DD; defaults to today (UTC)")
    p.add_argument("--manifest", default=str(Path(goldens.DEFAULT_LABELS_PATH).parent / "corpus_manifest.csv"))
    p.add_argument("--profiles", default=str(goldens.DEFAULT_PROFILES_PATH))
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    labeled_at = args.labeled_at or datetime.now(timezone.utc).date().isoformat()

    known_profiles = {p.id for p in goldens.load_profiles(args.profiles)}
    manifest = corpus_mod.load_manifest(args.manifest)
    known_filenames = set(manifest)
    if not known_filenames:
        print(
            f"WARNING: {args.manifest} has no entries — filename validation is a no-op. "
            f"Run scripts/eval_case_match_export.py first to produce it."
        )

    in_path = Path(args.in_path)
    rows_out: dict[tuple[str, str], dict] = {}
    errors: list[str] = []

    with in_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, raw in enumerate(reader, start=2):  # header is row 1
            profile_id = raw.get("profile_id", "").strip()
            filename = raw.get("filename", "").strip()
            label_raw = raw.get("ระดับความเกี่ยวข้อง (0/1/2)", "").strip()
            note = raw.get("หมายเหตุ", "").strip()

            if not profile_id or not filename:
                errors.append(f"row {i}: missing profile_id or filename")
                continue
            if known_profiles and profile_id not in known_profiles:
                errors.append(f"row {i}: unknown profile_id {profile_id!r}")
                continue
            if known_filenames and filename not in known_filenames:
                errors.append(f"row {i}: unknown filename {filename!r} (not in corpus manifest)")
                continue
            if label_raw not in _VALID_LABELS:
                errors.append(f"row {i}: relevance grade {label_raw!r} must be blank, 0, 1, or 2")
                continue

            key = (profile_id, filename)
            if key in rows_out:
                errors.append(f"row {i}: duplicate judgement for {key} (already seen earlier in this sheet)")
                continue

            rows_out[key] = {
                "profile_id": profile_id,
                "filename": filename,
                "label": int(label_raw) if label_raw else 0,
                "labeled_by": args.labeled_by,
                "labeled_at": labeled_at,
                "note": note,
            }

    if errors:
        print(f"ERROR: {len(errors)} problem(s) in {in_path}:")
        for e in errors[:50]:
            print(f"  - {e}")
        if len(errors) > 50:
            print(f"  ... and {len(errors) - 50} more")
        sys.exit(1)

    if not rows_out:
        print(f"ERROR: no valid rows found in {in_path}")
        sys.exit(1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows_out.values(), key=lambda r: (r["profile_id"], r["filename"]))
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["profile_id", "filename", "label", "labeled_by", "labeled_at", "note"])
        writer.writeheader()
        writer.writerows(ordered)

    n_strong = sum(1 for r in ordered if r["label"] == 2)
    n_some = sum(1 for r in ordered if r["label"] == 1)
    n_none = sum(1 for r in ordered if r["label"] == 0)
    profiles_covered = len({r["profile_id"] for r in ordered})
    print(f"Wrote {out_path}: {len(ordered)} judged pairs across {profiles_covered} profile(s)")
    print(f"  strong(2)={n_strong}  some(1)={n_some}  none(0)={n_none}")


if __name__ == "__main__":
    main()
