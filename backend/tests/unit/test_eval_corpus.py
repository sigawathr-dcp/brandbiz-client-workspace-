"""Unit tests for the pure (non-DB) helpers in app/eval/corpus.py: the
CorpusReport summary, filename resolution, and the manifest/sha-drift
staleness guard. load_corpus() itself is DB-touching and exercised by the
eval harness script against a real database, not here."""
from __future__ import annotations

import uuid

import pytest

from app.eval.corpus import (
    CorpusFile,
    CorpusReport,
    ManifestEntry,
    load_manifest,
    resolve_filenames,
    sha_drift,
    write_manifest,
)


def _cf(filename: str, file_id=None, sha="abc123", processed=True, chunks=2, embedded=2) -> CorpusFile:
    return CorpusFile(
        file_id=file_id or uuid.uuid4(),
        filename=filename,
        sha256_hash=sha,
        is_processed=processed,
        chunk_count=chunks,
        embedded_chunk_count=embedded,
    )


class TestCorpusReport:
    def test_healthy_report(self):
        report = CorpusReport(
            files=[_cf("a.md"), _cf("b.md")],
            duplicate_filenames={},
            unprocessed=[],
            zero_chunk=[],
            unembedded_chunk_files=[],
        )
        assert report.is_healthy()
        assert report.problems() == []

    def test_unhealthy_report_lists_every_problem(self):
        dup_id = uuid.uuid4()
        report = CorpusReport(
            files=[_cf("a.md")],
            duplicate_filenames={"dup.md": [dup_id, uuid.uuid4()]},
            unprocessed=[_cf("b.md", processed=False)],
            zero_chunk=[_cf("c.md", chunks=0, embedded=0)],
            unembedded_chunk_files=[_cf("d.md", chunks=3, embedded=1)],
        )
        assert not report.is_healthy()
        problems = report.problems()
        assert len(problems) == 4
        assert any("duplicate filename" in p for p in problems)
        assert any("is_processed=False" in p for p in problems)
        assert any("zero chunks" in p for p in problems)
        assert any("unembedded chunks" in p for p in problems)


class TestResolveFilenames:
    def test_maps_filename_to_file_id(self):
        fid = uuid.uuid4()
        report = CorpusReport(
            files=[_cf("case-study_a.md", file_id=fid)],
            duplicate_filenames={},
            unprocessed=[],
            zero_chunk=[],
            unembedded_chunk_files=[],
        )
        result = resolve_filenames(report)
        assert result == {"case-study_a.md": fid}

    def test_raises_on_duplicate_filenames(self):
        report = CorpusReport(
            files=[_cf("dup.md"), _cf("dup.md")],
            duplicate_filenames={"dup.md": [uuid.uuid4(), uuid.uuid4()]},
            unprocessed=[],
            zero_chunk=[],
            unembedded_chunk_files=[],
        )
        with pytest.raises(ValueError, match="duplicates present"):
            resolve_filenames(report)


class TestManifestRoundTrip:
    def test_write_then_load(self, tmp_path):
        path = tmp_path / "corpus_manifest.csv"
        entries = [
            ManifestEntry("b.md", "sha_b", "Title B", "Client B", "Cat B", 3),
            ManifestEntry("a.md", "sha_a", None, None, None, 1),
        ]
        write_manifest(path, entries)
        loaded = load_manifest(path)

        assert set(loaded) == {"a.md", "b.md"}
        assert loaded["b.md"].sha256 == "sha_b"
        assert loaded["b.md"].title == "Title B"
        assert loaded["a.md"].title is None
        assert loaded["a.md"].chunk_count == 1

    def test_missing_manifest_loads_empty(self, tmp_path):
        assert load_manifest(tmp_path / "does_not_exist.csv") == {}

    def test_output_is_sorted_by_filename(self, tmp_path):
        path = tmp_path / "m.csv"
        write_manifest(path, [ManifestEntry("z.md", "s", None, None, None, 1), ManifestEntry("a.md", "s", None, None, None, 1)])
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[1].startswith("a.md")
        assert lines[2].startswith("z.md")


class TestShaDrift:
    def test_no_drift_when_hashes_match(self):
        report = CorpusReport(
            files=[_cf("a.md", sha="same")],
            duplicate_filenames={},
            unprocessed=[],
            zero_chunk=[],
            unembedded_chunk_files=[],
        )
        manifest = {"a.md": ManifestEntry("a.md", "same", None, None, None, 2)}
        assert sha_drift(report, manifest) == []

    def test_drift_detected_when_hash_differs(self):
        report = CorpusReport(
            files=[_cf("a.md", sha="new_hash")],
            duplicate_filenames={},
            unprocessed=[],
            zero_chunk=[],
            unembedded_chunk_files=[],
        )
        manifest = {"a.md": ManifestEntry("a.md", "old_hash", None, None, None, 2)}
        assert sha_drift(report, manifest) == ["a.md"]

    def test_file_not_in_manifest_is_not_drift(self):
        # a brand-new file with no manifest entry yet isn't "stale" — it's unlabeled
        report = CorpusReport(
            files=[_cf("new_file.md")],
            duplicate_filenames={},
            unprocessed=[],
            zero_chunk=[],
            unembedded_chunk_files=[],
        )
        assert sha_drift(report, {}) == []
