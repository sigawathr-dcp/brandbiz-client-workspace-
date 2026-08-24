"""Publish intake script v2 — the spreadsheet-revised interview

Interview_Details.xlsx revises the interview: `history` ("เคยทำ branding
ไหม") is replaced by `asset_channel` (what the client already owns), `goal`
becomes `objective` and `horizon` becomes `timeframe`, and every option list
widens. It also assigns each question a matching tag and a weight, stored on
the columns migration 0059 added.

This publishes it as intake_scripts version 2 and flips v1 to
active = false. It deliberately does NOT touch existing
engagements.intake_script_id: an engagement mid-interview keeps answering
the script it started, and a finished one keeps the vocabulary its answers
were recorded under. Only new engagements get v2 —
services/engagement.py::get_active_script_id already resolves the highest
active version, so no code change is needed to cut over.

FROZEN. This migration used to import app.services.client_intake.
INTAKE_SCRIPT, because that literal WAS v2. v3 (migration 0062) has since
been authored, so the v2 script is inlined below verbatim, exactly as 0052
freezes v1. A published intake_scripts row must reproduce byte-for-byte on
a rebuilt database no matter how the live script later changes; importing
the live literal would have silently re-seeded v2 as v3's content and
reinterpreted every answer pinned to v2. See client_intake's module
docstring.

Revision ID: 0060_intake_script_v2
Revises: 0059_intake_weights
Create Date: 2026-08-21
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0060_intake_script_v2"
down_revision: Union[str, None] = "0059_intake_weights"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCRIPT_NAME = "Spreadsheet-revised 8-question script"

# The v2 script, frozen at publication. Do not edit: rows seeded from this
# literal are already pinned by live engagements.
_V2_SCRIPT: list[dict] = [
    {
        "field": "industry",
        "question": (
            "สวัสดีครับ ผมน้องภูมิ ที่ปรึกษาแบรนด์ของ Brandbiz ครับ 🙂\n"
            "ผมจะถามเรื่องธุรกิจของคุณ 8 ข้อ แล้วไปหาข้อมูลตลาดมาให้ "
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
        "field": "asset_channel",
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
        "question": "ขอบคุณครับ คำถามสุดท้ายก่อนผมไปหาข้อมูล — งบประมาณที่เตรียมไว้สำหรับโปรเจกต์นี้อยู่ประมาณช่วงไหนครับ?",
        "options": [
            {"label": "ต่ำกว่า 300,000 บาท", "value": "Under ฿300,000", "tag": "under_300k"},
            {"label": "300,000 – 800,000 บาท", "value": "฿300,000 - 800,000", "tag": "band_300_800k"},
            {"label": "800,000 – 1,500,000 บาท", "value": "฿800,000 - 1,500,000", "tag": "band_800_1500k"},
            {"label": "มากกว่า 1,500,000 บาท", "value": "฿1,500,000+", "tag": "over_1500k"},
            {"label": "ยังไม่แน่ใจ อยากให้ช่วยประเมิน", "value": "Not sure - needs guidance", "tag": "unsure"},
        ],
        "insight": "งบช่วงนี้บอกได้ว่าแผนจะครอบคลุมได้กว้างแค่ไหนตาม rate card จริง — ครบ 8 ข้อแล้วครับ ต่อไปผมจะไปหาข้อมูลตลาดจริงให้",
        "match_tag": "budget",
        "weight": None,
        "use_mode": "feasibility",
        "dev_note": "ไม่ควรใช้ตัด Case ที่เหมาะออกทันที — ใช้คัด Scope และ Plan & Budget หลัง Match Case แล้ว",
    },
]


def upgrade() -> None:
    conn = op.get_bind()

    weights = [s["weight"] for s in _V2_SCRIPT if s["use_mode"] == "match" and s["weight"]]
    total = round(sum(weights), 6)
    if total != 1.0:
        raise RuntimeError(f"v2 scoring weights must sum to 1.000, got {total}")

    conn.execute(text("UPDATE intake_scripts SET active = false WHERE locale = 'th'"))

    script_id = conn.execute(text("""
        INSERT INTO intake_scripts (version, locale, name, active)
        VALUES (2, 'th', :name, true)
        RETURNING id
    """), {"name": _SCRIPT_NAME}).scalar_one()

    for ordinal, step in enumerate(_V2_SCRIPT):
        question_id = conn.execute(text("""
            INSERT INTO intake_questions
                (script_id, ordinal, field_key, prompt, insight,
                 match_tag, weight, use_mode, dev_note)
            VALUES
                (:script_id, :ordinal, :field_key, :prompt, :insight,
                 :match_tag, :weight, :use_mode, :dev_note)
            RETURNING id
        """), {
            "script_id": script_id, "ordinal": ordinal,
            "field_key": step["field"], "prompt": step["question"],
            "insight": step.get("insight"),
            "match_tag": step.get("match_tag"), "weight": step.get("weight"),
            "use_mode": step.get("use_mode", "match"), "dev_note": step.get("dev_note"),
        }).scalar_one()

        for opt_ordinal, option in enumerate(step["options"]):
            conn.execute(text("""
                INSERT INTO intake_options (question_id, ordinal, label, value, tag_value)
                VALUES (:question_id, :ordinal, :label, :value, :tag_value)
            """), {
                "question_id": question_id, "ordinal": opt_ordinal,
                "label": option["label"], "value": option["value"],
                "tag_value": option.get("tag"),
            })


def downgrade() -> None:
    conn = op.get_bind()
    # Refuse to delete a script any engagement is pinned to — dropping it
    # would orphan real answers (intake_answers.question_id is ON DELETE
    # RESTRICT, but engagements.intake_script_id is not, so check explicitly).
    in_use = conn.execute(text("""
        SELECT count(*) FROM engagements e
        JOIN intake_scripts s ON s.id = e.intake_script_id
        WHERE s.version = 2 AND s.locale = 'th'
    """)).scalar_one()
    if in_use:
        raise RuntimeError(
            f"cannot drop intake script v2: {in_use} engagement(s) are pinned to it"
        )
    conn.execute(text("DELETE FROM intake_scripts WHERE version = 2 AND locale = 'th'"))
    conn.execute(text("UPDATE intake_scripts SET active = true WHERE version = 1 AND locale = 'th'"))
