"""
app/services/plan_edit_intent.py

Does a client's free-form chat turn ask to CHANGE their plan, as opposed to
asking a question about it?

Deliberately a keyword heuristic, not an LLM call, for two reasons:

  1. It runs on every client chat turn once a plan exists. An extra model
     round-trip per turn to answer a yes/no question is latency and cost the
     turn cannot earn back.
  2. It never decides anything on its own. A True here only makes the frontend
     offer a confirmation chip ("ปรับแผนให้เลย"); the revision itself is a
     separate, explicit POST /client/plan/revise. So a false positive costs one
     ignorable chip, and a false negative costs the client one rephrase — the
     asymmetry that would justify a model call isn't there.

Swappable: the whole contract is `detect(text) -> bool`. If the heuristic
proves too noisy in the field, replace the body with a classifier call and
nothing upstream changes.
"""

from __future__ import annotations

# Thai first — the client workspace is Thai-facing end to end (see
# services/plan.py::_build_drafting_prompt, which writes every plan string in
# Thai). English terms are here because staff preview the funnel in English.
_EDIT_TERMS = (
    # Thai: change / fix / adjust / swap
    "แก้ไข", "แก้", "ปรับ", "เปลี่ยน", "สลับ", "ทำใหม่", "ร่างใหม่",
    # Thai: add / remove / raise / cut
    "เพิ่ม", "ใส่", "เอาออก", "ตัด", "ลบ", "ลด", "ขยาย", "ย่อ", "ยืด",
    # English
    "change", "edit", "revise", "update", "rewrite", "redo", "adjust",
    "add ", "remove", "drop ", "increase", "decrease", "swap", "replace",
    "make it", "shorten", "extend",
)

# A turn carrying one of these is asking ABOUT the plan, not asking for it to
# change — "ทำไมงบเฟส 2 ถึงเพิ่มขึ้น" contains เพิ่ม but is a question.
_QUESTION_TERMS = (
    "ทำไม", "เพราะอะไร", "อย่างไร", "ยังไง", "คืออะไร", "อะไรคือ",
    "หมายความว่า", "อธิบาย", "ช่วยดู", "ขอดู",
    "why", "how come", "what is", "what's", "explain", "what does",
)

# Explicitly asking for the change anyway ("ช่วยปรับให้หน่อย") outranks a
# question word that happens to appear in the same sentence.
_IMPERATIVE_TERMS = (
    "ให้หน่อย", "หน่อย", "ให้เลย", "เลยครับ", "เลยค่ะ", "ขอให้", "อยากให้",
    "ต้องการให้", "please", "can you", "could you",
)

def _contains(haystack: str, terms: tuple[str, ...]) -> bool:
    return any(term in haystack for term in terms)


def detect(text: str) -> bool:
    """True when `text` reads as a request to change the plan.

    Thai does not delimit words with spaces, so this is substring matching, not
    tokenisation — which is why the term list leans on multi-character terms
    that do not appear inside unrelated words.
    """
    if not text or not text.strip():
        return False
    lowered = text.lower()

    if not _contains(lowered, _EDIT_TERMS):
        return False
    if _contains(lowered, _QUESTION_TERMS) and not _contains(lowered, _IMPERATIVE_TERMS):
        return False
    return True
