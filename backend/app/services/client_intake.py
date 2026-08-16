"""
app/services/client_intake.py

Deterministic 8-question intake for Client Workspaces (Phase 5 §3, D21/D22).

Ported from the approved design (`Brandbiz Workspace.dc.html`) — the script
IS the content, not a placeholder for a model to reconstruct. Advancing a
step is a database write, not an LLM call: at a live event, in front of
strangers, the intake must not derail, skip a question, ask two at once, or
answer in the wrong language — all things a local model driving free-form
turn-taking is unreliable at (see the plan's "Intake" decision).

Chip options are generic industry-neutral prompts (the mockup's scripted
coffee-shop answers were removed) — a client whose answer isn't covered
types it as free text via the "Skip" affordance.

Each INTAKE_SCRIPT entry is one turn: `question` is shown as น้องภูมิ's
message, `options` become the numbered chips (1-N keyboard shortcut, "Skip"
falls through to free text) rendered by components/client/IntakeChips.tsx.
Answering with a chip records `option["value"]`; free text is stored
verbatim. The mockup's own script data structure paired the CURRENT step's
`field` with the NEXT step's question text (the UI streamed one message
ahead of the field it was about to collect); this module un-shifts that so
`INTAKE_SCRIPT[i]` is self-contained: its own question, its own options, its
own field.

`insight` is what น้องภูมิ concluded from THIS step's answer — surfaced by
the frontend as an "insight earned" callout on the turn carrying the NEXT
question (see app/routers/client.py::answer_intake, which returns
`step_at(profile.step)["insight"]` before incrementing `profile.step`).
Industry-neutral, same as the questions.

After the last step, INTAKE_COMPLETE_MESSAGE is shown once, then the
frontend calls POST /client/research (see app/routers/client.py).

DB redesign note: INTAKE_SCRIPT below stays as the SEED literal — migration
0052 reads it once to populate intake_scripts/intake_questions/
intake_options, which is what the running app actually reads from
(*_db functions at the bottom of this module). Nothing at request time
reads INTAKE_SCRIPT directly anymore except the eval harness
(app/eval/goldens.py, query_variants.py), which deliberately stays
decoupled from real client data.
"""
from __future__ import annotations

import uuid
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intake import IntakeOption as IntakeOptionRow
from app.models.intake import IntakeQuestion as IntakeQuestionRow


class IntakeOption(TypedDict):
    label: str  # Thai chip text shown to the user
    value: str  # English value stored in the profile / used downstream


class IntakeStep(TypedDict):
    field: str
    question: str
    options: list[IntakeOption]
    insight: str


INTAKE_SCRIPT: list[IntakeStep] = [
    {
        "field": "industry",
        "question": (
            "สวัสดีครับ ผมน้องภูมิ ที่ปรึกษาแบรนด์ของ Brandbiz ครับ 🙂\n"
            "ผมจะถามเรื่องธุรกิจของคุณ 8 ข้อ แล้วไปหาข้อมูลตลาดมาให้ "
            "ก่อนจะร่างแผนพร้อมประมาณงบให้ครับ\n\n"
            "ข้อแรก — ธุรกิจของคุณทำอะไรครับ?"
        ),
        "options": [
            {"label": "ร้านอาหาร / คาเฟ่", "value": "Food & beverage / café"},
            {"label": "ค้าปลีก + ขายออนไลน์", "value": "Retail + online"},
            {"label": "ธุรกิจบริการ / B2B", "value": "Services / B2B"},
            {"label": "ความงาม / สุขภาพ", "value": "Beauty / health & wellness"},
            {"label": "ท่องเที่ยว / โรงแรม", "value": "Tourism / hospitality"},
            {"label": "อื่น ๆ — ผมพิมพ์เอง", "value": "Other (typed)"},
        ],
        "insight": "รู้ประเภทธุรกิจแล้วครับ — น้องภูมิ จะเทียบเคสจากไลบรารีเฉพาะหมวดเดียวกัน แทนที่จะเดาแบบกว้าง ๆ",
    },
    {
        "field": "stage",
        "question": "รับทราบครับ ธุรกิจของคุณอยู่ในระยะไหนแล้วครับ?",
        "options": [
            {"label": "โตแล้ว กำลังอยากขยาย", "value": "Growing, ready to expand"},
            {"label": "เปิดใหม่ ไม่เกิน 1 ปี", "value": "Under 1 year old"},
            {"label": "อยู่ตัวแล้ว แต่ยอดนิ่ง", "value": "Established, flat revenue"},
            {"label": "กำลังจะเปิด ยังไม่เริ่มขาย", "value": "Pre-launch"},
        ],
        "insight": "ระยะของธุรกิจบอกลำดับความสำคัญของแผนได้เยอะครับ — ธุรกิจที่โตแล้วมักพลาดตรงขยายก่อนที่รายได้ประจำจะนิ่ง",
    },
    {
        "field": "audience",
        "question": "เข้าใจแล้วครับ กลุ่มลูกค้าหลักของคุณคือใครครับ — คนแบบไหนที่เดินเข้ามาบ่อยที่สุด?",
        "options": [
            {"label": "คนวัยทำงานในเมือง", "value": "Urban working adults"},
            {"label": "นักเรียน นักศึกษา", "value": "Students"},
            {"label": "ครอบครัว และคนในละแวก", "value": "Families & neighbourhood"},
            {"label": "ลูกค้าธุรกิจ (B2B)", "value": "Business customers (B2B)"},
            {"label": "นักท่องเที่ยว / ชาวต่างชาติ", "value": "Tourists / foreigners"},
        ],
        "insight": "รู้กลุ่มเป้าหมายแล้ว — ข้อมูลตลาดที่น้องภูมิ จะไปค้นต่อจะกรองเฉพาะพฤติกรรมของคนกลุ่มนี้ ไม่ใช่ภาพรวมทั้งตลาด",
    },
    {
        "field": "challenge",
        "question": "ขอบคุณครับ 🙏 อะไรคือปัญหาใหญ่ที่สุดของคุณตอนนี้ครับ?",
        "options": [
            {"label": "คนยังไม่รู้จักแบรนด์", "value": "Low brand awareness"},
            {"label": "ยอดขายนิ่ง ไม่โตเท่าที่ควร", "value": "Flat / slow sales growth"},
            {"label": "กำไรบางเกินไป", "value": "Thin margins"},
            {"label": "คู่แข่งเยอะ หาจุดต่างยาก", "value": "Hard to differentiate from competitors"},
            {"label": "ช่องทางออนไลน์ยังไม่เวิร์ค", "value": "Online channels underperforming"},
        ],
        "insight": "ปัญหานี้คือสิ่งที่แผนจะแก้ก่อนเป็นอันดับแรก — เคสในไลบรารีที่แก้ปัญหาแบบเดียวกันจะถูกดึงมาเทียบให้",
    },
    {
        "field": "goal",
        "question": "ชัดเจนครับ แล้วเป้าหมายทางธุรกิจปีนี้ของคุณคืออะไรครับ?",
        "options": [
            {"label": "เพิ่มยอดขาย / ขยายสาขา", "value": "Grow sales / expand"},
            {"label": "สร้างแบรนด์ให้เป็นที่รู้จักมากขึ้น", "value": "Build brand awareness"},
            {"label": "รีเฟรชแบรนด์ทั้งระบบ", "value": "Full brand refresh"},
            {"label": "เปิดตัวสินค้า / บริการใหม่", "value": "Launch a new product / service"},
        ],
        "insight": "เป้าหมายชัดแล้วครับ — ขั้นตอนถัดไปในแผนจะเรียงลำดับให้ตรงเป้านี้โดยเฉพาะ ไม่ใช่แผนกว้าง ๆ ที่ทำทุกอย่างพร้อมกัน",
    },
    {
        "field": "horizon",
        "question": "ดีครับ อยากเห็นผลภายในกรอบเวลาเท่าไหร่ครับ?",
        "options": [
            {"label": "6 เดือน", "value": "6 months"},
            {"label": "3 เดือน — เร็วที่สุดเท่าที่ทำได้", "value": "3 months"},
            {"label": "12 เดือน", "value": "12 months"},
        ],
        "insight": "กรอบเวลานี้กำหนดจังหวะของแผนได้ครับ — บางเป้าหมาย (เช่นรีแบรนด์ทั้งระบบ) ต้องใช้เวลามากกว่ากรอบสั้น ๆ ผมจะจัดลำดับให้เหมาะกัน",
    },
    {
        "field": "budget",
        "question": "รับทราบครับ งบที่คุณเตรียมไว้อยู่ประมาณช่วงไหนครับ?",
        "options": [
            {"label": "ต่ำกว่า 300,000 บาท", "value": "Under ฿300,000"},
            {"label": "300,000 – 800,000 บาท", "value": "฿300,000 - 800,000"},
            {"label": "800,000 – 1,200,000 บาท", "value": "฿800,000 - 1,200,000"},
            {"label": "มากกว่า 1,200,000 บาท", "value": "฿1,200,000+"},
            {"label": "ยังไม่แน่ใจ อยากให้ช่วยประเมิน", "value": "Not sure - needs guidance"},
        ],
        "insight": "งบช่วงนี้บอกได้ว่าแผนจะครอบคลุมได้กว้างแค่ไหนตาม rate card จริง — ทุกบรรทัดที่เสนอจะยึดตัวเลขนี้ ไม่มีการเดาราคา",
    },
    {
        "field": "history",
        "question": "ขอบคุณครับ คำถามสุดท้ายก่อนผมไปหาข้อมูล — เคยทำงานด้าน branding มาก่อนไหมครับ?",
        "options": [
            {"label": "เคยจ้างฟรีแลนซ์ทำโลโก้ครั้งเดียว", "value": "One freelance logo project"},
            {"label": "ยังไม่เคยเลย", "value": "None"},
            {"label": "มีทีม in-house ดูอยู่", "value": "In-house team"},
            {"label": "เคยทำกับเอเจนซี่มาแล้ว", "value": "Worked with an agency before"},
        ],
        "insight": "ประวัติด้าน branding บอกว่าแผนควรเริ่มจากศูนย์หรือต่อยอดของเดิม — ครบ 8 ข้อแล้วครับ ต่อไปผมจะไปหาข้อมูลตลาดจริงให้",
    },
]

INTAKE_COMPLETE_MESSAGE = (
    "ครบแล้วครับ 🙏 ผมขออนุญาตไปดูข้อมูลตลาดและคู่แข่งในธุรกิจของคุณก่อนสักครู่นะครับ"
)

FIELD_LABELS: dict[str, str] = {
    "industry": "Business",
    "stage": "Stage",
    "audience": "Audience",
    "challenge": "Challenge",
    "goal": "Goal",
    "horizon": "Horizon",
    "budget": "Budget band",
    "history": "Brand history",
}


def total_steps() -> int:
    return len(INTAKE_SCRIPT)


def field_manifest() -> list[dict]:
    """Ordered [{key, label, options}] for every intake field — the display
    contract for the frontend Profile tab (WorkPanel.tsx), served on GET
    /client/bootstrap so adding/renaming a step here can never desync the
    frontend's field list or its completeness math. `options` (each
    {index, label}) lets the Profile tab's edit mode render the same chips
    the intake used, rather than keeping its own copy of the script."""
    return [
        {
            "key": step["field"],
            "label": FIELD_LABELS.get(step["field"], step["field"]),
            "options": [{"index": i, "label": o["label"]} for i, o in enumerate(step["options"])],
        }
        for step in INTAKE_SCRIPT
    ]


def step_at(index: int) -> IntakeStep | None:
    """Return the step at `index`, or None once intake is complete."""
    if 0 <= index < len(INTAKE_SCRIPT):
        return INTAKE_SCRIPT[index]
    return None


def index_of_field(field: str) -> int | None:
    """Resolve a field key to its position in INTAKE_SCRIPT — used by the
    profile-edit endpoint to check "has this question already been
    answered" (idx < profile.step) without duplicating the script order."""
    for i, step in enumerate(INTAKE_SCRIPT):
        if step["field"] == field:
            return i
    return None


async def total_steps_db(session: AsyncSession, script_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(IntakeQuestionRow).where(IntakeQuestionRow.script_id == script_id)
    )
    return result.scalar_one()


async def _questions(session: AsyncSession, script_id: uuid.UUID) -> list[IntakeQuestionRow]:
    result = await session.execute(
        select(IntakeQuestionRow).where(IntakeQuestionRow.script_id == script_id).order_by(IntakeQuestionRow.ordinal)
    )
    return list(result.scalars().all())


async def field_manifest_db(session: AsyncSession, script_id: uuid.UUID) -> list[dict]:
    """DB-backed replacement for field_manifest() — ordered
    [{key, label, options}] for every intake field, read from the script
    an engagement was actually given (engagements.intake_script_id) rather
    than the live Python literal, so a republished script never changes
    what an in-progress engagement's Profile tab renders."""
    questions = await _questions(session, script_id)
    out = []
    for q in questions:
        opt_result = await session.execute(
            select(IntakeOptionRow).where(IntakeOptionRow.question_id == q.id).order_by(IntakeOptionRow.ordinal)
        )
        options = list(opt_result.scalars().all())
        out.append({
            "key": q.field_key,
            "label": FIELD_LABELS.get(q.field_key, q.field_key),
            "options": [{"index": i, "label": o.label} for i, o in enumerate(options)],
        })
    return out


async def step_at_db(session: AsyncSession, script_id: uuid.UUID, index: int) -> IntakeStep | None:
    """DB-backed replacement for step_at() — returns the same IntakeStep
    shape (field/question/options/insight) so resolve_answer() and the
    router's response builders are unchanged."""
    questions = await _questions(session, script_id)
    if not (0 <= index < len(questions)):
        return None
    q = questions[index]
    opt_result = await session.execute(
        select(IntakeOptionRow).where(IntakeOptionRow.question_id == q.id).order_by(IntakeOptionRow.ordinal)
    )
    options = list(opt_result.scalars().all())
    return {
        "field": q.field_key,
        "question": q.prompt,
        "options": [{"label": o.label, "value": o.value} for o in options],
        "insight": q.insight or "",
    }


async def option_id_at_db(session: AsyncSession, question_id: uuid.UUID, option_index: int) -> uuid.UUID | None:
    result = await session.execute(
        select(IntakeOptionRow.id).where(IntakeOptionRow.question_id == question_id).order_by(IntakeOptionRow.ordinal)
    )
    options = list(result.scalars().all())
    if not (0 <= option_index < len(options)):
        return None
    return options[option_index]


async def question_id_at_db(session: AsyncSession, script_id: uuid.UUID, index: int) -> uuid.UUID | None:
    questions = await _questions(session, script_id)
    if not (0 <= index < len(questions)):
        return None
    return questions[index].id


async def index_of_field_db(session: AsyncSession, script_id: uuid.UUID, field: str) -> int | None:
    questions = await _questions(session, script_id)
    for i, q in enumerate(questions):
        if q.field_key == field:
            return i
    return None


def resolve_answer(step: IntakeStep, *, option_index: int | None, free_text: str | None) -> str:
    """Resolve what gets stored for a step's field: a chip's value, or the
    raw free-text answer when the user skipped the chips (see
    components/client/IntakeChips.tsx "Skip" affordance)."""
    if option_index is not None:
        if not (0 <= option_index < len(step["options"])):
            raise ValueError("option_index out of range")
        return step["options"][option_index]["value"]
    if free_text is not None and free_text.strip():
        return free_text.strip()
    raise ValueError("either option_index or non-empty free_text is required")
