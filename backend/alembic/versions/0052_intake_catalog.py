"""Create + seed the intake question catalog (DB redesign, stage 2)

intake_scripts -> intake_questions -> intake_options replaces the Python
literal INTAKE_SCRIPT (app/services/client_intake.py) as the runtime
source of truth for the interview's questions. Reordering or inserting a
question now publishes a new `intake_scripts` version rather than silently
reinterpreting every engagement's already-stored answers (each engagement
pins the script version it was given via engagements.intake_script_id).

The version-1 script is FROZEN as _V1_SCRIPT below rather than imported
from app.services.client_intake. That module's INTAKE_SCRIPT means "the
current script" and has since moved on to v2 (migration 0060); importing
it here would make a fresh `alembic upgrade head` seed v2 content under
version = 1. A migration's data must be immutable, so it is inlined.

Also backfills intake_script_id onto every engagement created by 0051
(that migration ran before this catalog existed).

Revision ID: 0052_intake_catalog
Revises: 0051_engagements_backfill
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0052_intake_catalog"
down_revision: Union[str, None] = "0051_engagements_backfill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_V1_SCRIPT: list[dict] = [
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


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS intake_scripts (
            id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            version        INTEGER       NOT NULL,
            locale         VARCHAR(8)    NOT NULL DEFAULT 'th',
            name           VARCHAR(255)  NOT NULL,
            active         BOOLEAN       NOT NULL DEFAULT true,
            published_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
            CONSTRAINT uq_intake_scripts_version_locale UNIQUE (version, locale)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS intake_questions (
            id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            script_id      UUID          NOT NULL REFERENCES intake_scripts(id) ON DELETE CASCADE,
            ordinal        SMALLINT      NOT NULL,
            field_key      VARCHAR(64)   NOT NULL,
            prompt         TEXT          NOT NULL,
            insight        TEXT,
            CONSTRAINT uq_intake_questions_script_ordinal UNIQUE (script_id, ordinal),
            CONSTRAINT uq_intake_questions_script_field UNIQUE (script_id, field_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_questions_script_id ON intake_questions (script_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS intake_options (
            id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            question_id    UUID          NOT NULL REFERENCES intake_questions(id) ON DELETE CASCADE,
            ordinal        SMALLINT      NOT NULL,
            label          TEXT          NOT NULL,
            value          VARCHAR(255)  NOT NULL,
            CONSTRAINT uq_intake_options_question_ordinal UNIQUE (question_id, ordinal)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_intake_options_question_id ON intake_options (question_id)")

    op.execute("""
        ALTER TABLE engagements
        ADD CONSTRAINT fk_engagements_intake_script
        FOREIGN KEY (intake_script_id) REFERENCES intake_scripts(id) ON DELETE RESTRICT
    """)

    conn = op.get_bind()

    script_id = conn.execute(text("""
        INSERT INTO intake_scripts (version, locale, name, active)
        VALUES (1, 'th', 'Original 8-question script', true)
        RETURNING id
    """)).scalar_one()

    for ordinal, step in enumerate(_V1_SCRIPT):
        question_id = conn.execute(text("""
            INSERT INTO intake_questions (script_id, ordinal, field_key, prompt, insight)
            VALUES (:script_id, :ordinal, :field_key, :prompt, :insight)
            RETURNING id
        """), {
            "script_id": script_id, "ordinal": ordinal,
            "field_key": step["field"], "prompt": step["question"], "insight": step.get("insight"),
        }).scalar_one()

        for opt_ordinal, option in enumerate(step["options"]):
            conn.execute(text("""
                INSERT INTO intake_options (question_id, ordinal, label, value)
                VALUES (:question_id, :ordinal, :label, :value)
            """), {
                "question_id": question_id, "ordinal": opt_ordinal,
                "label": option["label"], "value": option["value"],
            })

    conn.execute(text("UPDATE engagements SET intake_script_id = :sid WHERE intake_script_id IS NULL"),
                 {"sid": script_id})


def downgrade() -> None:
    op.execute("ALTER TABLE engagements DROP CONSTRAINT IF EXISTS fk_engagements_intake_script")
    op.execute("UPDATE engagements SET intake_script_id = NULL")
    op.execute("DROP TABLE IF EXISTS intake_options")
    op.execute("DROP TABLE IF EXISTS intake_questions")
    op.execute("DROP TABLE IF EXISTS intake_scripts")
