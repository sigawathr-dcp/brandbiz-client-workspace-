"""
app/services/client_intake.py

Deterministic 9-question intake for Client Workspaces (Phase 5 §3, D21/D22).

Ported from the approved design (`Brandbiz Workspace.dc.html`) — the script
IS the content, not a placeholder for a model to reconstruct. Advancing a
step is a database write, not an LLM call: at a live event, in front of
strangers, the intake must not derail, skip a question, ask two at once, or
answer in the wrong language — all things a local model driving free-form
turn-taking is unreliable at (see the plan's "Intake" decision).

Chip options are generic industry-neutral prompts (the mockup's scripted
coffee-shop answers were removed) — a client whose answer isn't covered
types it as free text via the "อื่นๆ" row IntakeChips renders under every
question. There is no Skip: the option card is the only way to answer a
step, and ClientWorkspace keeps the composer locked while it is up.

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

DB redesign note: INTAKE_SCRIPT below means THE CURRENT SCRIPT — today v3,
seeded into intake_scripts/intake_questions/intake_options by migration
0062, which is what the running app actually reads from (*_db functions at
the bottom of this module). Per-turn intake reads the DB, but two constants
derived from this literal ARE read at request time — SCORING_WEIGHTS (via
app/services/case_match.py) and case_taxonomy.VOCAB — so editing a weight
here rescores every engagement, including ones pinned to an older script.
That is a known gap against migration 0059's intent; see SCORING_WEIGHTS
below. The eval harness (app/eval/goldens.py, query_variants.py) also reads
the literal, deliberately decoupled from real client data.

Superseded versions are NOT kept here: v1 is frozen inside migration 0052,
v2 inside migration 0060. Publishing v4 means editing INTAKE_SCRIPT, adding
a migration, and freezing v3 into 0062 the same way — never mutating a
published intake_scripts row, because every engagement pins the script it
was interviewed with (engagements.intake_script_id) and a live answer must
never be reinterpreted against a vocabulary it was not collected under.
FIELD_LABELS / THAI_FIELD_LABELS therefore stay a union across versions.
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intake import IntakeOption as IntakeOptionRow
from app.models.intake import IntakeQuestion as IntakeQuestionRow


class IntakeOption(TypedDict):
    label: str  # Thai chip text shown to the user
    value: str  # English value stored in the profile / used downstream
    tag: str  # controlled-vocab token (app/services/case_taxonomy.py)


class IntakeStep(TypedDict):
    field: str
    question: str
    options: list[IntakeOption]
    # True when the client may pick SEVERAL chips for this question (the six
    # "match" questions). Feasibility and trigger questions stay single-pick:
    # a budget band or platform-dependency level is one fact, not a set.
    # Stored per question in intake_questions.multi_select (migration 0064).
    multi_select: bool
    insight: str
    match_tag: str | None  # case_study_tags.tag_type this field scores against
    weight: float | None  # share of the match score; None => non-scoring
    # "match"           -> weighted into the case-match score (weight is set)
    # "feasibility"      -> shapes scope / pricing downstream (weight is None)
    # "solution_trigger" -> fires a post-diagnosis recommendation rule and is
    #                       deliberately kept OUT of the score (weight is None);
    #                       see app/services/solution_trigger.py
    use_mode: str
    dev_note: str | None  # rule / caveat for matching logic; never shown to the client


# Interview v3 — the DSME script (Questions for DSMEs.xlsx).
#
# The only change from v2 is a ninth question, `own_commerce`, inserted at
# position 5 (between `challenge` and `asset_channel`, as the sheet numbers
# it): how much of the client's revenue depends on external, GP-charging
# platforms. Every other question, option list, tag and weight is unchanged
# from v2, which lives on, frozen, in migration 0060.
#
# `own_commerce` is the first question with use_mode "solution_trigger". The
# sheet is explicit that it must not enter the match score
# ("ไม่ใช้คำนวณ Similarity Score / Case Matching โดยตรง") — it is a rule
# evaluated AFTER diagnosis, reading asset_channel and objective alongside
# it, to decide whether the plan should propose an owned commerce channel /
# LINE Microsite / CRM. That rule is app/services/solution_trigger.py; this
# entry only declares the question and its vocabulary.
#
# Because the trigger carries no weight, the six scoring weights still sum to
# 1.000 and no case ranking moves — enforced by test_client_intake.py.
#
# `weight` / `match_tag` / `use_mode` carry the sheet's Matching Tag and
# Weight columns into intake_questions (migration 0059).
#
# Every option list stops at 9: IntakeChips binds 1-N to single digits via
# parseInt(e.key), so a 10th option would be unreachable from the keyboard.
# The sheet's explicit "อื่น ๆ (พิมพ์ระบุ)" rows are omitted for the same
# budget — IntakeChips already renders an "อื่นๆ" free-text row under every
# question, so listing it as an option would duplicate that row.
INTAKE_SCRIPT: list[IntakeStep] = [
    {
        "field": "industry",
        "multi_select": True,
        "question": (
            "สวัสดีครับ ผมน้องภูมิ ที่ปรึกษาแบรนด์ของ Brandbiz ครับ 🙂\n"
            "ผมจะถามเรื่องธุรกิจของคุณ 9 ข้อ แล้วไปหาข้อมูลตลาดมาให้ "
            "ก่อนจะร่างแผนพร้อมประมาณงบให้ครับ\n\n"
            "ข้อแรก — ธุรกิจของคุณอยู่ในกลุ่มไหนครับ?"
        ),
        "options": [
            {"label": "ความงาม / สกินแคร์ / เครื่องสำอาง", "value": "Beauty / skincare / cosmetics", "tag": "beauty"},
            {"label": "สุขภาพ / อาหารเสริม", "value": "Health / supplements", "tag": "health_supplement"},
            {"label": "อาหาร / เครื่องดื่ม / ร้านอาหาร / Food Delivery", "value": "Food & beverage / restaurant / delivery", "tag": "food_beverage"},
            {"label": "ค้าปลีก / E-Commerce / FMCG", "value": "Retail / e-commerce / FMCG", "tag": "retail_fmcg"},
            {"label": "Application / Tech / Digital Service", "value": "Application / tech / digital service", "tag": "tech_app"},
            {"label": "Entertainment / Media", "value": "Entertainment / media", "tag": "entertainment_media"},
            {"label": "Automotive", "value": "Automotive", "tag": "automotive"},
            {"label": "B2B / Service", "value": "B2B / service", "tag": "b2b_service"},
            {"label": "Property / Travel / Hospitality", "value": "Property / travel / hospitality", "tag": "property_travel"},
        ],
        "insight": "รู้กลุ่มธุรกิจแล้วครับ — น้องภูมิ จะเทียบเคสจากไลบรารีในหมวดเดียวกันและหมวดใกล้เคียงก่อน แทนที่จะเดาแบบกว้าง ๆ",
        "match_tag": "industry",
        "weight": 0.25,
        "use_mode": "match",
        "dev_note": "ควรเป็นตัวกรองหลัก แต่ไม่ใช่เงื่อนไขตายตัว — ใช้ INDUSTRY_ADJACENCY ให้เครดิตบางส่วนกับหมวดใกล้เคียง",
    },
    {
        "field": "stage",
        "multi_select": True,
        "question": "รับทราบครับ ตอนนี้ธุรกิจของคุณอยู่ในช่วงไหนครับ?",
        "options": [
            {"label": "กำลังจะเปิด / ยังไม่เริ่มขาย", "value": "Pre-launch", "tag": "pre_launch"},
            {"label": "เปิดใหม่ ไม่เกิน 1 ปี", "value": "Under 1 year old", "tag": "early"},
            {"label": "โตแล้ว กำลังอยากขยาย", "value": "Growing, ready to expand", "tag": "growth"},
            {"label": "อยู่ตัวแล้ว แต่ยอดเริ่มนิ่ง / โตช้า", "value": "Established, flat or slow growth", "tag": "plateau"},
            {"label": "ต้องการ Reposition / เปิดตลาดใหม่", "value": "Repositioning / entering a new market", "tag": "reposition"},
            {"label": "Enterprise / Regional Expansion", "value": "Enterprise / regional expansion", "tag": "enterprise"},
        ],
        "insight": "ระยะของธุรกิจบอกลำดับความสำคัญของแผนได้เยอะครับ — ธุรกิจที่โตแล้วมักพลาดตรงขยายก่อนที่รายได้ประจำจะนิ่ง",
        "match_tag": "stage",
        "weight": 0.05,
        "use_mode": "match",
        "dev_note": "ดีกว่าถามยอดขายต่อปี เพราะตอบง่ายและช่วย match มากกว่า",
    },
    {
        "field": "audience",
        "multi_select": True,
        "question": "เข้าใจแล้วครับ กลุ่มลูกค้าหลักที่คุณอยากเจาะคือใครครับ?",
        "options": [
            {"label": "Gen Z / นักเรียน / นักศึกษา", "value": "Gen Z / students", "tag": "gen_z_student"},
            {"label": "คนวัยทำงาน / First Jobber", "value": "Working adults / first jobbers", "tag": "working_adult"},
            {"label": "ครอบครัว / ผู้ใหญ่ / 35+", "value": "Families / adults 35+", "tag": "family_35plus"},
            {"label": "ลูกค้าธุรกิจ (B2B)", "value": "Business customers (B2B)", "tag": "b2b"},
            {"label": "Fandom / Community", "value": "Fandom / community", "tag": "fandom_community"},
            {"label": "นักท่องเที่ยว / ตลาดต่างประเทศ", "value": "Tourists / overseas markets", "tag": "tourist_overseas"},
            {"label": "Mass Market / หลายกลุ่ม", "value": "Mass market / multiple segments", "tag": "mass_market"},
        ],
        "insight": "รู้กลุ่มเป้าหมายแล้ว — ข้อมูลตลาดที่น้องภูมิ จะไปค้นต่อจะกรองเฉพาะพฤติกรรมของคนกลุ่มนี้ ไม่ใช่ภาพรวมทั้งตลาด",
        "match_tag": "audience",
        "weight": 0.10,
        "use_mode": "match",
        "dev_note": None,
    },
    {
        "field": "challenge",
        "multi_select": True,
        "question": "ขอบคุณครับ 🙏 ตอนนี้ปัญหาที่อยากแก้มากที่สุดคือข้อไหนครับ?",
        "options": [
            {"label": "คนยังไม่รู้จักแบรนด์ / Awareness ต่ำ", "value": "Low brand awareness", "tag": "low_awareness"},
            {"label": "ยอดขายหรือ Conversion โตช้า", "value": "Slow sales or conversion growth", "tag": "slow_conversion"},
            {"label": "แบรนด์ไม่ต่างจากคู่แข่ง / Positioning ยังไม่ชัด", "value": "Weak differentiation / unclear positioning", "tag": "weak_positioning"},
            {"label": "Social / Content / Engagement ยังไม่สร้าง Impact", "value": "Social / content / engagement lacks impact", "tag": "weak_engagement"},
            {"label": "ทำ Campaign แล้วคนหาย ไม่ได้ Data กลับมา", "value": "Campaigns capture no data", "tag": "no_data_capture"},
            {"label": "มีลูกค้าแต่ซื้อซ้ำต่ำ / CRM ยังไม่แข็งแรง", "value": "Low repeat purchase / weak CRM", "tag": "low_retention"},
            {"label": "ต้องการเปิดตัวสินค้า / เปิดตลาดใหม่", "value": "Need to launch a product / enter a new market", "tag": "launch_need"},
            {"label": "Data กระจัดกระจาย / งาน Manual เยอะ", "value": "Fragmented data / heavy manual work", "tag": "fragmented_data"},
            {"label": "ต้องการ Reposition / Premiumize แบรนด์", "value": "Need to reposition / premiumize the brand", "tag": "reposition_premiumize"},
        ],
        "insight": "ปัญหานี้คือสิ่งที่แผนจะแก้ก่อนเป็นอันดับแรก — เคสในไลบรารีที่แก้ปัญหาแบบเดียวกันจะถูกดึงมาเทียบให้",
        "match_tag": "challenge",
        "weight": 0.25,
        "use_mode": "match",
        "dev_note": "ควรให้น้ำหนักเท่า Industry",
    },
    {
        "field": "own_commerce",
        "multi_select": False,
        "question": (
            "เข้าใจปัญหาแล้วครับ อีกเรื่องที่อยากรู้ — ตอนนี้ยอดขายของธุรกิจคุณ"
            "พึ่งช่องทางที่ต้องเสียค่าธรรมเนียม / GP หรือแพลตฟอร์มภายนอกมากแค่ไหนครับ?"
        ),
        "options": [
            {"label": "มาก — ยอดขายหลักมาจาก Marketplace / Delivery / Platform และค่า GP ค่อนข้างสูง", "value": "Heavy - mostly marketplace / delivery / platform, high GP", "tag": "platform_heavy"},
            {"label": "ปานกลาง — มีทั้งช่องทางของตัวเองและ Platform ภายนอก", "value": "Mixed - own channels plus external platforms", "tag": "platform_mixed"},
            {"label": "น้อย — ยอดขายส่วนใหญ่มาจากช่องทางของแบรนด์เอง", "value": "Light - mostly the brand own channels", "tag": "owned_dominant"},
            {"label": "ยังไม่มีช่องทางขายของตัวเอง", "value": "No owned sales channel yet", "tag": "no_owned_channel"},
            {"label": "ไม่เกี่ยวข้องกับธุรกิจของฉัน", "value": "Not applicable to my business", "tag": "not_applicable"},
        ],
        "insight": "ข้อนี้สำคัญกับกำไรระยะยาวครับ — ยิ่งยอดขายพึ่งแพลตฟอร์มภายนอกมาก ค่า GP ก็ยิ่งกินมาร์จิ้นไปเรื่อย ๆ น้องภูมิ จะดูให้ว่าควรเสนอช่องทางขายของแบรนด์เองควบคู่ไปด้วยไหม",
        "match_tag": "own_commerce",
        "weight": None,
        "use_mode": "solution_trigger",
        "dev_note": "ไม่ใช้คำนวณ Similarity Score / Case Matching โดยตรง ใช้เป็น Trigger หลัง Diagnosis หากพึ่ง Platform สูงหรือยังไม่มีช่องทางขายของตัวเอง ให้ AI พิจารณา Own Commerce / LINE Microsite โดยดู Existing Assets / Channel และ Business Objective ประกอบ",
    },
    {
        "field": "asset_channel",
        "multi_select": True,
        "question": "ชัดเจนครับ ตอนนี้ธุรกิจมีช่องทางหรือฐานลูกค้าอะไรอยู่แล้วบ้างครับ?",
        "options": [
            {"label": "Social Media เป็นหลัก", "value": "Mainly social media", "tag": "social_only"},
            {"label": "Marketplace / E-Commerce", "value": "Marketplace / e-commerce", "tag": "marketplace"},
            {"label": "LINE OA แต่ยังไม่ได้ทำ CRM / เก็บ Data จริงจัง", "value": "LINE OA without real CRM / data capture", "tag": "line_oa_no_crm"},
            {"label": "Website / E-Commerce + Social", "value": "Website / e-commerce plus social", "tag": "web_plus_social"},
            {"label": "มี Customer Database / CRM แล้ว", "value": "Existing customer database / CRM", "tag": "has_crm"},
            {"label": "มีหน้าร้าน / Event / Offline Touchpoint", "value": "Storefront / events / offline touchpoints", "tag": "offline_touchpoint"},
            {"label": "มีหลายช่องทาง แต่ Data ยังแยกกัน", "value": "Multiple channels with siloed data", "tag": "multi_channel_siloed"},
            {"label": "ยังไม่มีฐานลูกค้าของตัวเอง", "value": "No owned customer base yet", "tag": "no_owned_base"},
        ],
        "insight": "รู้แล้วว่าคุณมีอะไรอยู่ในมือ — แผนจะต่อยอดจากช่องทางเดิมก่อน แทนที่จะให้เริ่มสร้างใหม่ทั้งหมด",
        "match_tag": "asset_channel",
        "weight": 0.15,
        "use_mode": "match",
        "dev_note": "ข้อนี้แทนคำถาม 'เคยทำ Branding ไหม' ซึ่งช่วย Case Match น้อยกว่า",
    },
    {
        "field": "objective",
        "multi_select": True,
        "question": "ดีครับ ผลลัพธ์หลักที่อยากได้จากโปรเจกต์นี้คืออะไรครับ?",
        "options": [
            {"label": "สร้าง Brand Awareness", "value": "Build brand awareness", "tag": "awareness"},
            {"label": "เปิดตัวสินค้า / แคมเปญใหม่", "value": "Launch a product / new campaign", "tag": "launch"},
            {"label": "เพิ่มยอดขาย / หาลูกค้าใหม่", "value": "Grow sales / acquire new customers", "tag": "sales_acquisition"},
            {"label": "เก็บ Lead / First-party Data", "value": "Capture leads / first-party data", "tag": "lead_data"},
            {"label": "เพิ่มการซื้อซ้ำ / CRM / Loyalty", "value": "Increase repeat purchase / CRM / loyalty", "tag": "retention_loyalty"},
            {"label": "สร้าง Engagement / Community / Fandom", "value": "Build engagement / community / fandom", "tag": "engagement_community"},
            {"label": "Reposition / Premiumization", "value": "Reposition / premiumization", "tag": "reposition"},
            {"label": "ขยายตลาดใหม่ / ต่างประเทศ", "value": "Expand into new / overseas markets", "tag": "market_expansion"},
            {"label": "เชื่อม Online–Offline / O2O", "value": "Connect online and offline / O2O", "tag": "o2o"},
        ],
        "insight": "เป้าหมายชัดแล้วครับ — ขั้นตอนถัดไปในแผนจะเรียงลำดับให้ตรงเป้านี้โดยเฉพาะ ไม่ใช่แผนกว้าง ๆ ที่ทำทุกอย่างพร้อมกัน",
        "match_tag": "objective",
        "weight": 0.20,
        "use_mode": "match",
        "dev_note": "ทับซ้อนกับ challenge โดยตั้งใจ — ความสอดคล้องของสองข้อนี้เป็นสัญญาณในตัวเอง",
    },
    {
        "field": "timeframe",
        "multi_select": False,
        "question": "รับทราบครับ อยากเริ่มหรือเห็นผลภายในกรอบเวลาประมาณไหนครับ?",
        "options": [
            {"label": "เร่งด่วน ภายใน 1–3 เดือน", "value": "Urgent - within 1-3 months", "tag": "urgent_1_3m"},
            {"label": "3–6 เดือน", "value": "3-6 months", "tag": "mid_3_6m"},
            {"label": "6–12 เดือน", "value": "6-12 months", "tag": "long_6_12m"},
            {"label": "ยังยืดหยุ่นได้", "value": "Flexible", "tag": "flexible"},
        ],
        "insight": "กรอบเวลานี้กำหนดจังหวะของแผนได้ครับ — บางเป้าหมาย (เช่นรีแบรนด์ทั้งระบบ) ต้องใช้เวลามากกว่ากรอบสั้น ๆ ผมจะจัดลำดับให้เหมาะกัน",
        "match_tag": "timeframe",
        "weight": None,
        "use_mode": "feasibility",
        "dev_note": "ใช้วางแผนและตัด Scope ไม่ควรใช้เป็นตัวเลือก Case หลัก",
    },
    {
        "field": "budget",
        "multi_select": False,
        "question": "ขอบคุณครับ คำถามสุดท้ายก่อนผมไปหาข้อมูล — งบประมาณที่เตรียมไว้สำหรับโปรเจกต์นี้อยู่ประมาณช่วงไหนครับ?",
        "options": [
            {"label": "ต่ำกว่า 300,000 บาท", "value": "Under ฿300,000", "tag": "under_300k"},
            {"label": "300,000 – 800,000 บาท", "value": "฿300,000 - 800,000", "tag": "band_300_800k"},
            {"label": "800,000 – 1,500,000 บาท", "value": "฿800,000 - 1,500,000", "tag": "band_800_1500k"},
            {"label": "มากกว่า 1,500,000 บาท", "value": "฿1,500,000+", "tag": "over_1500k"},
            {"label": "ยังไม่แน่ใจ อยากให้ช่วยประเมิน", "value": "Not sure - needs guidance", "tag": "unsure"},
        ],
        "insight": "งบช่วงนี้บอกได้ว่าแผนจะครอบคลุมได้กว้างแค่ไหนตาม rate card จริง — ครบ 9 ข้อแล้วครับ ต่อไปผมจะไปหาข้อมูลตลาดจริงให้",
        "match_tag": "budget",
        "weight": None,
        "use_mode": "feasibility",
        "dev_note": "ไม่ควรใช้ตัด Case ที่เหมาะออกทันที — ใช้คัด Scope และ Plan & Budget หลัง Match Case แล้ว",
    },
]

# Joins the option values of a multi-select answer into the single display
# string that _load_fields / the transcript / build_context_query carry
# ("Beauty / skincare / cosmetics; Health / supplements"). "; " because
# option values themselves contain both "," and "/" — the scorer splits the
# stored string back apart on this token (split_answer_values), so the
# joiner must never appear inside a single option value; guarded by
# test_client_intake.py.
ANSWER_JOINER = "; "


def join_answer_values(values: list[str]) -> str:
    return ANSWER_JOINER.join(values)


def split_answer_values(value: str) -> list[str]:
    """Inverse of join_answer_values for a loaded profile value. A
    single-select or free-text answer comes back as a one-element list; a
    free text that happens to contain '; ' splits into pieces no chip value
    matches, which downstream treats exactly like unsplit free text."""
    return [p for p in (s.strip() for s in value.split(ANSWER_JOINER)) if p]


INTAKE_COMPLETE_MESSAGE = (
    "ครบแล้วครับ 🙏 ผมขออนุญาตไปดูข้อมูลตลาดและคู่แข่งในธุรกิจของคุณก่อนสักครู่นะครับ"
)

# Keyed by field, and deliberately a UNION of the v1 and v2 vocabularies: an
# engagement interviewed on script v1 still has `goal` / `horizon` / `history`
# answers to render in the Profile tab and to embed in the case-match query.
# Missing keys degrade to the raw field name via .get(k, k), but a v1 label
# reading "goal" in the UI is a regression, so both sets are listed.
FIELD_LABELS: dict[str, str] = {
    # v3 only
    "own_commerce": "Platform dependency",
    # v2
    "industry": "Business",
    "stage": "Stage",
    "audience": "Audience",
    "challenge": "Challenge",
    "asset_channel": "Existing channels",
    "objective": "Objective",
    "timeframe": "Timeframe",
    "budget": "Budget band",
    # v1 only
    "goal": "Goal",
    "horizon": "Horizon",
    "history": "Brand history",
}

# Thai counterpart of FIELD_LABELS. The split is English-vs-Thai, not
# prod-vs-eval: FIELD_LABELS feeds the bge-m3 embedding query
# (case_match.build_context_query) and the Profile tab; these feed anything
# that must read as Thai to a Thai reader — the market-scan prompt
# (routers/client.py::_build_research_query) and the eval labeling sheet
# (app/eval/goldens.py, query_variants.py).
THAI_FIELD_LABELS: dict[str, str] = {
    # v3 only
    "own_commerce": "การพึ่งแพลตฟอร์มภายนอก",
    # v2
    "industry": "ธุรกิจ",
    "stage": "ระยะ",
    "audience": "ลูกค้า",
    "challenge": "ปัญหา",
    "asset_channel": "ช่องทางที่มีอยู่",
    "objective": "เป้าหมาย",
    "timeframe": "กรอบเวลา",
    "budget": "งบ",
    # v1 only
    "goal": "เป้าหมาย",
    "horizon": "กรอบเวลา",
    "history": "ประสบการณ์",
}

# Fields that contribute to the weighted case-match score, keyed by the
# case_study_tags.tag_type they score against — derived from INTAKE_SCRIPT so
# the sheet's Weight column has exactly one home. Both non-"match" modes are
# deliberately absent: "feasibility" (timeframe, budget) shapes scope and
# pricing downstream, and "solution_trigger" (own_commerce) fires a
# recommendation rule — neither may decide which cases surface.
#
# Caveat, inherited from v2: this is a module-level constant read live by
# case_match.py, NOT per-script-version state read from intake_questions.
# Migration 0059 stores weight/use_mode per version so that a reweight could
# be a new script version rather than a deploy, but nothing reads those
# columns at match time yet. Until that is wired up, editing a weight here
# silently rescores engagements pinned to older scripts.
SCORING_WEIGHTS: dict[str, float] = {
    step["match_tag"]: step["weight"]
    for step in INTAKE_SCRIPT
    if step["use_mode"] == "match" and step["weight"] is not None and step["match_tag"]
}


# Fields whose answers must never influence WHICH case studies surface.
# Today that is `own_commerce` alone, per its sheet note: "ไม่ใช้คำนวณ
# Similarity Score / Case Matching โดยตรง".
#
# Keeping it out of SCORING_WEIGHTS is only half the job. The match score is
# alpha * tag_score + (1 - alpha) * dense_score, and the dense half embeds a
# flattened string of the profile — so a field that is merely absent from the
# weights still moves rankings through the embedding, silently and with no
# breakdown row to show for it. match_query_fields() below is the chokepoint
# that closes that path.
TRIGGER_FIELDS: frozenset[str] = frozenset(
    step["field"] for step in INTAKE_SCRIPT if step["use_mode"] == "solution_trigger"
)


def match_query_fields(fields: Mapping[str, str]) -> list[str]:
    """The answered fields that may shape a case-match query, in interview
    order — the single source of truth for every builder that embeds a
    profile (case_match.build_context_query and each eval variant in
    app/eval/query_variants.py, which exist to be compared against it).

    Solution-trigger fields are dropped. Fields the CURRENT script does not
    define are kept and appended in sorted order: an engagement pinned to an
    older script answered slots this one no longer has (v1's goal / horizon /
    history), and filtering to the current script's keys would silently
    shrink an old client's query and change which cases they match.

    Not used by the market-scan prompt (routers/client.py::
    _build_research_query). That prompt researches the client's market rather
    than ranking anything, and platform dependency is legitimate context for
    it — the sheet's restriction is on case matching specifically.
    """
    ordered = [
        step["field"] for step in INTAKE_SCRIPT if step["field"] not in TRIGGER_FIELDS
    ]
    known = {step["field"] for step in INTAKE_SCRIPT}
    trailing = sorted(k for k in fields if k not in known)
    return [k for k in [*ordered, *trailing] if k in fields]


def total_steps() -> int:
    return len(INTAKE_SCRIPT)


def field_manifest() -> list[dict]:
    """Ordered [{key, label, options}] for every intake field — the display
    contract for the frontend Profile tab (WorkPanel.tsx), served on GET
    /client/bootstrap so adding/renaming a step here can never desync the
    frontend's field list or its completeness math. `options` (each
    {index, label, value}) lets the Profile tab's edit mode render the same
    chips the intake used, rather than keeping its own copy of the script.

    `value` is what resolve_answer() would store for that chip — the same
    string the profile holds — so edit mode can mark which chip is the
    CURRENT answer. Matching on `label` cannot do that: labels are Thai and
    stored values are English."""
    return [
        {
            "key": step["field"],
            "label": FIELD_LABELS.get(step["field"], step["field"]),
            "multi_select": step["multi_select"],
            "options": [
                {"index": i, "label": o["label"], "value": o["value"]}
                for i, o in enumerate(step["options"])
            ],
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
            "multi_select": q.multi_select,
            "options": [
                {"index": i, "label": o.label, "value": o.value}
                for i, o in enumerate(options)
            ],
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
        "multi_select": q.multi_select,
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


async def option_ids_at_db(
    session: AsyncSession, question_id: uuid.UUID, option_indices: list[int]
) -> list[uuid.UUID] | None:
    """Resolve several chip indices at once (a multi-select answer), in
    ordinal order regardless of pick order — the same normalisation
    resolve_answers() applies to the stored values. None if any index is
    out of range."""
    result = await session.execute(
        select(IntakeOptionRow.id).where(IntakeOptionRow.question_id == question_id).order_by(IntakeOptionRow.ordinal)
    )
    options = list(result.scalars().all())
    if any(not (0 <= i < len(options)) for i in option_indices):
        return None
    return [options[i] for i in sorted(set(option_indices))]


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


def resolve_answers(
    step: IntakeStep, *, option_indices: list[int] | None, free_text: str | None
) -> list[str]:
    """Resolve what gets stored for a step's field: one value per picked
    chip, or the single raw free-text answer when the user skipped the chips
    (see components/client/IntakeChips.tsx "อื่นๆ" affordance).

    More than one chip is only legal on a multi-select question. Indices are
    deduped and returned in ordinal order, so the same picks always store
    the same value list regardless of click order.
    """
    if option_indices:
        indices = sorted(set(option_indices))
        if len(indices) > 1 and not step.get("multi_select"):
            raise ValueError("this question accepts a single choice")
        for i in indices:
            if not (0 <= i < len(step["options"])):
                raise ValueError("option_index out of range")
        return [step["options"][i]["value"] for i in indices]
    if free_text is not None and free_text.strip():
        return [free_text.strip()]
    raise ValueError("either option_index or non-empty free_text is required")


def resolve_answer(step: IntakeStep, *, option_index: int | None, free_text: str | None) -> str:
    """Single-choice wrapper around resolve_answers() — kept because a
    single answer is still the only legal shape for non-multi questions and
    the older call sites/tests use it."""
    values = resolve_answers(
        step,
        option_indices=[option_index] if option_index is not None else None,
        free_text=free_text,
    )
    return values[0]
