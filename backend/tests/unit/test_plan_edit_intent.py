"""Unit tests for the plan-edit intent heuristic.

This is the piece most likely to be tuned in the field, so the cases are
written as behaviour ("a question about the budget is not an edit request")
rather than as assertions about the keyword lists — swapping the body for a
classifier should leave this file passing unchanged.

The asymmetry that justifies a heuristic over a model call: a True only
surfaces a confirmation chip, so a false positive costs one ignorable chip and
a false negative costs the client one rephrase. See the module docstring.
"""
from __future__ import annotations

import pytest

from app.services.plan_edit_intent import detect


@pytest.mark.parametrize("text", [
    "ตัดเฟส 4 ออก แล้วเพิ่มงบ content หน่อย",   # cut phase 4, add content budget
    "ขอปรับแผนให้เน้น B2B มากขึ้น",              # adjust the plan toward B2B
    "เปลี่ยนชื่อแผนเป็น 'แผนส่งออกลาว'",          # rename the plan
    "ลดงบเฟส 3 ลงครึ่งหนึ่ง",                    # halve phase 3's budget
    "change the budget for phase 2",
    "please remove the PR retainer",
])
def test_edit_requests_are_detected(text):
    assert detect(text) is True


@pytest.mark.parametrize("text", [
    "ทำไมงบเฟส 2 ถึงเพิ่มขึ้น",        # why did phase 2's budget go up — contains เพิ่ม
    "แผนนี้คืออะไร",                   # what is this plan
    "อธิบายเฟส 3 ให้ฟังหน่อย",          # explain phase 3 — contains หน่อย
    "สวัสดีครับ",                       # hello
    "why is phase 2 more expensive",
    "what is the contingency for",
    "",
    "   ",
])
def test_questions_and_chatter_are_not_edit_requests(text):
    assert detect(text) is False


def test_an_explicit_request_outranks_a_question_word():
    """"ช่วยปรับให้หน่อย ทำไมมันแพงจัง" is a client asking for the change AND
    grumbling about the price. The ask is the actionable half."""
    assert detect("ช่วยปรับให้หน่อย ทำไมมันแพงจัง") is True
