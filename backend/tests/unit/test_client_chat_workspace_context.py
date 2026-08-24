"""Unit tests for the workspace-journey blocks POST /client/chat injects as
system context.

Why this exists at all: steps 1-3 produce artifacts that live OUTSIDE the
message thread — the interview is intake_answers rows (services/client_intake.py
runs it as a deterministic DB flow, not as LLM turns), the market scan is
research_findings, the case match is case_matches. chat_policy.
load_history_messages() only ever reads `messages`, so none of it reached the
model: the chat re-asked what น้องภูมิ had already collected, and "ทำไมถึงเลือก
เคสนี้ให้" hit a model that had never seen the cards on the client's screen.

DB-free — the same mocked-session style as test_client_chat_plan_context.py.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers import client as client_router


class _FakeCtx:
    def __init__(self):
        self.user = MagicMock(id=uuid.uuid4())
        self.workspace_id = uuid.uuid4()


# ---------------------------------------------------------------------------
# _intake_chat_context — the client profile
# ---------------------------------------------------------------------------

def _turn(text: str):
    return MagicMock(text=text)


def _transcript(*pairs: tuple[str, str]):
    """_intake_transcript's shape: alternating (question, answer) turns."""
    turns = []
    for question, answer in pairs:
        turns.extend([_turn(question), _turn(answer)])
    return AsyncMock(return_value=turns)


_PAIRS = (
    ("ธุรกิจของคุณอยู่ในอุตสาหกรรมไหน", "ร้านกาแฟ"),
    ("เป้าหมายหลักในปีนี้คืออะไร", "เพิ่มยอดขายหน้าร้าน 30%"),
)


async def _intake_block(transcript):
    with patch.object(client_router, "_intake_transcript", transcript):
        return await client_router._intake_chat_context(AsyncMock(), MagicMock())


async def test_answered_questions_reach_the_model():
    block = await _intake_block(_transcript(*_PAIRS))

    assert "[CLIENT PROFILE" in block
    for question, answer in _PAIRS:
        assert f"- {question} → {answer}" in block


async def test_answers_are_ordered_as_the_script_asked_them():
    """_intake_transcript orders by IntakeQuestion.ordinal; pairing must not
    scramble that — a profile read out of order reads as a different client."""
    block = await _intake_block(_transcript(*_PAIRS))

    assert block.index(_PAIRS[0][1]) < block.index(_PAIRS[1][1])


async def test_a_seat_that_has_not_answered_anything_gets_no_block():
    """An engagement created but not yet interviewed must leave prepare_chat's
    system prompt exactly as it was — an empty block, not an empty header."""
    assert await _intake_block(_transcript()) == ""


async def test_a_partly_finished_interview_still_reaches_the_model():
    """The block is not gated on the interview being done: half a profile is
    still a list of things the chat must not ask a second time."""
    block = await _intake_block(_transcript(_PAIRS[0]))

    assert _PAIRS[0][1] in block
    assert _PAIRS[1][1] not in block


async def test_a_pasted_intake_essay_is_truncated():
    """Free-text answers are whatever the client pasted. One of them must not
    eat chat_policy._HISTORY_CHAR_BUDGET's room to generate."""
    essay = "ก" * (client_router._INTAKE_CONTEXT_VALUE_CHARS + 500)
    block = await _intake_block(_transcript(("เล่าเรื่องแบรนด์ให้ฟังหน่อย", essay)))

    assert "ก" * client_router._INTAKE_CONTEXT_VALUE_CHARS + "…" in block
    assert essay not in block


# ---------------------------------------------------------------------------
# _research_chat_context — the market scan
# ---------------------------------------------------------------------------

_FINDINGS = [
    {"text": "ตลาดกาแฟพิเศษในไทยโต 12% ต่อปี [1]"},
    {"text": "ลูกค้า Gen Z ให้ความสำคัญกับที่มาของเมล็ด [2]"},
]
_CITATIONS = [
    {"index": 1, "source": "https://example.com/coffee-market"},
    {"index": 2, "source": "https://example.com/genz"},
]


async def _research_block(*, status="done", findings=None, citations=None, run=True):
    out = {
        "id": str(uuid.uuid4()),
        "findings": _FINDINGS if findings is None else findings,
        "citations": _CITATIONS if citations is None else citations,
    }
    with patch.object(
        client_router,
        "_latest_research_run",
        AsyncMock(return_value=MagicMock(id=uuid.uuid4(), status=status) if run else None),
    ), patch.object(client_router, "_research_out", AsyncMock(return_value=out)):
        return await client_router._research_chat_context(AsyncMock(), MagicMock())


async def test_market_scan_findings_and_sources_reach_the_model():
    block = await _research_block()

    assert "[MARKET SCAN" in block
    for finding in _FINDINGS:
        assert finding["text"] in block
    for citation in _CITATIONS:
        assert f"[{citation['index']}] {citation['source']}" in block


async def test_findings_keep_their_citation_markers_verbatim():
    """The [n] markers are reproduced alongside the source list, so the text
    they are attached to must not be rewritten on the way in."""
    block = await _research_block()

    assert "[1]" in block and "[2]" in block


async def test_a_scan_that_has_not_finished_is_not_quoted():
    """A running scan has no findings yet and a failed one has none at all —
    either way the client is not looking at numbers to explain."""
    assert await _research_block(status="running") == ""
    assert await _research_block(status="failed") == ""


async def test_a_seat_that_never_ran_a_scan_gets_no_block():
    assert await _research_block(run=False) == ""


async def test_a_finished_but_empty_scan_gets_no_block():
    """'Ran, found nothing' must not become a header promising findings."""
    assert await _research_block(findings=[]) == ""


async def test_a_runaway_scan_is_capped():
    many = [{"text": f"finding {i}"} for i in range(client_router._RESEARCH_CONTEXT_FINDINGS + 5)]
    block = await _research_block(findings=many)

    assert many[0]["text"] in block
    assert many[-1]["text"] not in block


async def test_a_long_finding_is_truncated():
    long_finding = [{"text": "x" * (client_router._RESEARCH_CONTEXT_TEXT_CHARS + 200)}]
    block = await _research_block(findings=long_finding)

    assert "x" * client_router._RESEARCH_CONTEXT_TEXT_CHARS + "…" in block
    assert long_finding[0]["text"] not in block


# ---------------------------------------------------------------------------
# _cases_chat_context — the matched case studies
# ---------------------------------------------------------------------------

def _match(**over):
    base = {
        "file_id": str(uuid.uuid4()),
        "filename": "brandbiz-case-01.pdf",
        "score": 0.82,
        "rationale": "โจทย์เรื่องการสร้างแบรนด์ร้านกาแฟท้องถิ่นใกล้เคียงกัน",
        "title": "Local Coffee Rebrand",
        "client": "ร้านกาแฟบ้านสวน",
        "category": "Brand Strategy",
        "source_url": "https://example.com/case",
        "summary": "รีแบรนด์ร้านกาแฟท้องถิ่นให้ขายได้ทั้งหน้าร้านและออนไลน์",
        "image_url": None,
        "matched_on": ["อุตสาหกรรม", "เป้าหมาย"],
    }
    base.update(over)
    return base


async def _cases_block(*, status="done", matches=None, run=True):
    rows = {"matches": [_match()] if matches is None else matches}
    with patch.object(
        client_router,
        "_latest_case_run",
        AsyncMock(return_value=MagicMock(id=uuid.uuid4(), status=status) if run else None),
    ), patch.object(client_router, "_case_matches_for_run", AsyncMock(return_value=rows)):
        return await client_router._cases_chat_context(AsyncMock(), MagicMock())


async def test_matched_cases_reach_the_model():
    m = _match()
    block = await _cases_block(matches=[m])

    assert "[MATCHED CASE STUDIES" in block
    assert m["title"] in block
    assert m["client"] in block
    assert m["category"] in block
    assert m["rationale"] in block
    assert m["summary"] in block
    assert "ตรงกับ: อุตสาหกรรม, เป้าหมาย" in block


async def test_the_score_is_quoted_exactly_as_the_card_shows_it():
    """_case_matches_for_run already rounded it. A chat turn quoting a
    different figure than the card next to it reads as a contradiction."""
    block = await _cases_block(matches=[_match(score=0.82)])

    assert "(score 0.82)" in block


async def test_cases_keep_the_engines_ranking():
    ranked = [_match(title="First", score=0.9), _match(title="Second", score=0.7)]
    block = await _cases_block(matches=ranked)

    assert block.index("1. First") < block.index("2. Second")


async def test_a_case_without_a_parsed_card_falls_back_to_its_filename():
    """Corpus rows whose card never parsed have title None — the block must
    still name the case rather than emitting a blank heading."""
    block = await _cases_block(matches=[_match(title=None, client=None)])

    assert "1. brandbiz-case-01.pdf" in block


async def test_a_match_run_that_has_not_finished_is_not_quoted():
    assert await _cases_block(status="running") == ""
    assert await _cases_block(status="failed") == ""


async def test_a_seat_that_never_matched_gets_no_block():
    assert await _cases_block(run=False) == ""


async def test_a_finished_run_with_no_matches_gets_no_block():
    """'Ran, matched nothing' is a real outcome (see CaseMatchExecution) and
    must not become a header promising cards."""
    assert await _cases_block(matches=[]) == ""


async def test_only_the_cards_the_client_sees_are_described():
    many = [_match(title=f"Case {i}") for i in range(client_router._CASES_CONTEXT_MATCHES + 3)]
    block = await _cases_block(matches=many)

    assert "Case 0" in block
    assert f"Case {client_router._CASES_CONTEXT_MATCHES + 2}" not in block


async def test_a_long_corpus_summary_is_truncated():
    long_summary = "y" * (client_router._CASES_CONTEXT_SUMMARY_CHARS + 300)
    block = await _cases_block(matches=[_match(summary=long_summary)])

    assert "y" * client_router._CASES_CONTEXT_SUMMARY_CHARS + "…" in block
    assert long_summary not in block


# ---------------------------------------------------------------------------
# _workspace_chat_context — the three blocks together
# ---------------------------------------------------------------------------

async def _workspace(profile="[CLIENT PROFILE]", research="[MARKET SCAN]", cases="[CASES]"):
    ctx = _FakeCtx()
    svc = AsyncMock()
    svc.get_or_create_active = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
    with patch.object(client_router, "engagement_svc", svc), \
            patch.object(client_router, "_intake_chat_context", AsyncMock(return_value=profile)), \
            patch.object(client_router, "_research_chat_context", AsyncMock(return_value=research)), \
            patch.object(client_router, "_cases_chat_context", AsyncMock(return_value=cases)):
        return await client_router._workspace_chat_context(AsyncMock(), ctx), svc, ctx


async def test_the_blocks_are_joined_in_journey_order():
    block, _, _ = await _workspace()

    assert block.index("[CLIENT PROFILE]") < block.index("[MARKET SCAN]") < block.index("[CASES]")


async def test_empty_blocks_leave_no_blank_gaps():
    """A seat mid-interview has no scan and no cases; the profile must arrive
    on its own rather than trailed by empty separators."""
    block, _, _ = await _workspace(research="", cases="")

    assert block == "[CLIENT PROFILE]"


async def test_a_seat_at_the_very_start_contributes_nothing():
    block, _, _ = await _workspace(profile="", research="", cases="")

    assert block == ""


async def test_the_engagement_is_resolved_once_for_all_three_blocks():
    """Three helpers, one lookup — and off the caller's context, never an id
    the client supplied (the same forced-scope rule as agent_id)."""
    _, svc, ctx = await _workspace()

    svc.get_or_create_active.assert_awaited_once()
    assert svc.get_or_create_active.await_args.args[1:] == (ctx.user, ctx.workspace_id)
    assert [c.args[2] for c in svc.get_step.await_args_list] == ["interview", "market", "cases"]
