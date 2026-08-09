"""Unit tests for app.services.vault_sync — the Obsidian vault reconcile.

Uses real temp-directory trees (walk_vault, extract_text, sha256_of_path all
run for real against tmp_path) but mocks everything that would touch a real
DB/blob-store/embedder (save_upload, process_file, and the session itself),
following the pattern in test_chat_policy.py.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.classifier as classifier_module
from app.models.classification import DataTier
from app.models.file import File
from app.services import vault_sync
from app.services.classifier import _compile_rules


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_classifier_rules():
    """Vault sync must work whether or not classification rules are loaded;
    each test sets what it needs and we reset afterwards."""
    classifier_module._RULES = []
    yield
    classifier_module._RULES = []


def _thai_id_rule():
    return SimpleNamespace(
        name="Thai National ID",
        pattern_type="regex",
        pattern=r"\d-\d{4}-\d{5}-\d{2}-\d",
        detected_tier="TIER_3_CONFIDENTIAL",
    )


def _fake_session(existing_rows: list[File]):
    """An AsyncSession stand-in whose first execute() returns `existing_rows`
    for the `SELECT * FROM files WHERE source='obsidian'` query; later
    execute() calls (updates/deletes inside _update_note/_remove_note) reuse
    the same mock result, which is fine since those callers discard it."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = existing_rows

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=cm)
    return factory, session


def _existing_file(source_path: str, sha: str, is_processed: bool = True) -> File:
    return File(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        filename=Path(source_path).name,
        s3_key=f"bot/{source_path}",
        sha256_hash=sha,
        detected_tier=DataTier.TIER_1_PUBLIC.value,
        is_processed=is_processed,
        scope="org",
        source="obsidian",
        source_path=source_path,
    )


# ---------------------------------------------------------------------------
# walk_vault — exclusion rules
# ---------------------------------------------------------------------------

class TestWalkVault:
    def test_excludes_reserved_dirs_and_non_extractable_files(self, tmp_path):
        (tmp_path / ".obsidian").mkdir()
        (tmp_path / ".obsidian" / "config.json").write_text("{}")
        (tmp_path / ".trash").mkdir()
        (tmp_path / ".trash" / "deleted.md").write_text("gone")
        (tmp_path / "templates").mkdir()
        (tmp_path / "templates" / "daily.md").write_text("template")
        (tmp_path / "notes").mkdir()
        (tmp_path / "notes" / "a.md").write_text("real note")
        (tmp_path / "img.png").write_bytes(b"\x89PNG")
        (tmp_path / "board.canvas").write_text("{}")

        tree = vault_sync.walk_vault(tmp_path, templates_dirname="templates")

        assert set(tree.keys()) == {"notes/a.md"}

    def test_includes_all_extractable_suffixes(self, tmp_path):
        for name in ("a.md", "b.txt", "c.csv", "d.pdf", "e.docx"):
            (tmp_path / name).write_bytes(b"x")

        tree = vault_sync.walk_vault(tmp_path, templates_dirname="templates")

        assert set(tree.keys()) == {"a.md", "b.txt", "c.csv", "d.pdf", "e.docx"}


# ---------------------------------------------------------------------------
# Reconcile: add / update / skip / delete / rename
# ---------------------------------------------------------------------------

class TestReconcileAddUpdateSkip:
    async def test_add_new_note(self, tmp_path, _silence_audit_celery):
        (tmp_path / "note.md").write_text("hello world")
        factory, session = _fake_session([])
        bot_id = uuid.uuid4()

        with patch("app.services.vault_sync.save_upload", return_value=tmp_path / "blob") as mock_save, \
             patch("app.services.vault_sync.process_file", new=AsyncMock()) as mock_process:
            summary = await vault_sync.sync_vault(factory, bot_id, tmp_path)

        assert summary.added == 1
        assert summary.updated == summary.deleted == summary.quarantined == 0
        mock_save.assert_called_once()
        mock_process.assert_awaited_once()

        added_file = session.add.call_args.args[0]
        assert isinstance(added_file, File)
        assert added_file.source == "obsidian"
        assert added_file.source_path == "note.md"
        assert added_file.scope == "org"  # shared vault must be org-searchable
        assert added_file.user_id == bot_id

        actions = [c.kwargs["action"] for c in _silence_audit_celery.call_args_list]
        assert "vault_note_ingested" in actions

    async def test_update_note_on_content_change_keeps_same_file_id(self, tmp_path, _silence_audit_celery):
        (tmp_path / "note.md").write_text("new content")
        existing = _existing_file("note.md", sha="old-sha")
        factory, session = _fake_session([existing])

        with patch("app.services.vault_sync.save_upload", return_value=tmp_path / "blob") as mock_save, \
             patch("app.services.vault_sync.process_file", new=AsyncMock()) as mock_process:
            summary = await vault_sync.sync_vault(factory, uuid.uuid4(), tmp_path)

        assert summary.updated == 1
        assert summary.added == summary.deleted == summary.quarantined == 0
        # save_upload called with the *existing* file_id/filename — same identity.
        mock_save.assert_called_once_with(existing.user_id, existing.id, existing.filename, b"new content")
        mock_process.assert_awaited_once_with(existing.id)

        actions = [c.kwargs["action"] for c in _silence_audit_celery.call_args_list]
        assert "vault_note_updated" in actions

    async def test_skip_unchanged_note_no_extraction_or_embed(self, tmp_path, _silence_audit_celery):
        content = b"unchanged"
        (tmp_path / "note.md").write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        existing = _existing_file("note.md", sha=sha, is_processed=True)
        factory, session = _fake_session([existing])

        with patch("app.services.vault_sync.save_upload") as mock_save, \
             patch("app.services.vault_sync.process_file", new=AsyncMock()) as mock_process, \
             patch("app.services.vault_sync.extract_text") as mock_extract:
            summary = await vault_sync.sync_vault(factory, uuid.uuid4(), tmp_path)

        assert summary.skipped == 1
        assert summary.added == summary.updated == summary.deleted == summary.quarantined == 0
        mock_save.assert_not_called()
        mock_process.assert_not_awaited()
        mock_extract.assert_not_called()  # sha-gated skip must avoid extraction entirely

    async def test_unprocessed_row_is_retried_even_if_sha_unchanged(self, tmp_path, _silence_audit_celery):
        """A note whose prior ingest failed (is_processed=False) must keep
        retrying on unchanged content, not be silently skipped forever."""
        content = b"retry me"
        (tmp_path / "note.md").write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        existing = _existing_file("note.md", sha=sha, is_processed=False)
        factory, session = _fake_session([existing])

        with patch("app.services.vault_sync.save_upload", return_value=tmp_path / "blob"), \
             patch("app.services.vault_sync.process_file", new=AsyncMock()) as mock_process:
            summary = await vault_sync.sync_vault(factory, uuid.uuid4(), tmp_path)

        assert summary.updated == 1
        assert summary.skipped == 0
        mock_process.assert_awaited_once()


class TestReconcileDeleteRename:
    async def test_delete_note_missing_from_tree(self, tmp_path, _silence_audit_celery):
        existing = _existing_file("gone.md", sha="whatever")
        factory, session = _fake_session([existing])  # empty tmp_path -> tree has nothing

        with patch("app.services.vault_sync.delete_blob") as mock_delete_blob:
            summary = await vault_sync.sync_vault(factory, uuid.uuid4(), tmp_path)

        assert summary.deleted == 1
        assert summary.added == summary.updated == summary.quarantined == 0
        mock_delete_blob.assert_called_once_with(existing.user_id, existing.id, existing.filename)

        actions = [c.kwargs["action"] for c in _silence_audit_celery.call_args_list]
        assert "vault_note_deleted" in actions

    async def test_rename_is_delete_old_plus_add_new(self, tmp_path, _silence_audit_celery):
        (tmp_path / "new_name.md").write_text("same content, new path")
        existing = _existing_file("old_name.md", sha="stale-sha")
        factory, session = _fake_session([existing])

        with patch("app.services.vault_sync.save_upload", return_value=tmp_path / "blob"), \
             patch("app.services.vault_sync.process_file", new=AsyncMock()), \
             patch("app.services.vault_sync.delete_blob") as mock_delete_blob:
            summary = await vault_sync.sync_vault(factory, uuid.uuid4(), tmp_path)

        assert summary.added == 1
        assert summary.deleted == 1
        mock_delete_blob.assert_called_once_with(existing.user_id, existing.id, existing.filename)


# ---------------------------------------------------------------------------
# Confidentiality quarantine
# ---------------------------------------------------------------------------

class TestQuarantine:
    async def test_tier3_note_is_not_ingested(self, tmp_path, _silence_audit_celery):
        classifier_module._RULES = _compile_rules([_thai_id_rule()])
        (tmp_path / "secret.md").write_text("My ID is 1-2345-67890-12-1, please help.")
        factory, session = _fake_session([])

        with patch("app.services.vault_sync.save_upload") as mock_save, \
             patch("app.services.vault_sync.process_file", new=AsyncMock()) as mock_process:
            summary = await vault_sync.sync_vault(factory, uuid.uuid4(), tmp_path)

        assert summary.quarantined == 1
        assert summary.added == 0
        mock_save.assert_not_called()
        mock_process.assert_not_awaited()
        session.add.assert_not_called()

        actions = [c.kwargs["action"] for c in _silence_audit_celery.call_args_list]
        assert "vault_note_quarantined" in actions

    async def test_previously_clean_note_removed_when_it_turns_confidential(self, tmp_path, _silence_audit_celery):
        classifier_module._RULES = _compile_rules([_thai_id_rule()])
        (tmp_path / "note.md").write_text("My ID is 1-2345-67890-12-1, please help.")
        existing = _existing_file("note.md", sha="old-clean-sha")  # sha differs -> reclassify
        factory, session = _fake_session([existing])

        with patch("app.services.vault_sync.delete_blob") as mock_delete_blob:
            summary = await vault_sync.sync_vault(factory, uuid.uuid4(), tmp_path)

        assert summary.quarantined == 1
        mock_delete_blob.assert_called_once_with(existing.user_id, existing.id, existing.filename)

        actions = [c.kwargs["action"] for c in _silence_audit_celery.call_args_list]
        assert "vault_note_quarantined" in actions


# ---------------------------------------------------------------------------
# Raw markdown ingestion (no wikilink/frontmatter preprocessing)
# ---------------------------------------------------------------------------

class TestRawMarkdownIngestion:
    async def test_wikilinks_and_frontmatter_reach_classifier_unmodified(self, tmp_path, _silence_audit_celery):
        raw = "---\ntitle: Secret\n---\nSee [[Other Note|alias]] and %%a comment%%."
        (tmp_path / "note.md").write_text(raw, encoding="utf-8")
        factory, session = _fake_session([])

        captured: dict[str, str] = {}

        def _capture_tier(text: str) -> DataTier:
            captured["text"] = text
            return DataTier.TIER_1_PUBLIC

        with patch("app.services.vault_sync.detect_tier", side_effect=_capture_tier), \
             patch("app.services.vault_sync.save_upload", return_value=tmp_path / "blob"), \
             patch("app.services.vault_sync.process_file", new=AsyncMock()):
            await vault_sync.sync_vault(factory, uuid.uuid4(), tmp_path)

        # No stripping of frontmatter/wikilinks/comments — ingest raw per decision #7.
        assert "[[Other Note|alias]]" in captured["text"]
        assert "%%a comment%%" in captured["text"]
        assert "title: Secret" in captured["text"]
