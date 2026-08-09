# CH-AI Gateway — Slide Additions & Edits

Ready-to-paste Thai copy for `CH-AI_Gateway_Product_Presentation.pdf`. Organized
by slide, in the order they should appear in the deck. Each block matches the
existing format: `SECTION LABEL` (all caps eyebrow) → Thai headline → cards/body
→ italic footer takeaway. Insert points are given relative to the current
20-page deck.

Background on why these exist: `PLAN.md` in the repo (this product's build
plan) shows several enterprise features are already shipped — role-based model
access, automatic data-tier classification, the Policy Engine, 4-eyes Reveal,
per-role quotas — that the current deck barely mentions. It also names **MCP
connector** as the extension mechanism, but the shipped integration is an
OpenAI-compatible `/v1` API + n8n webhooks; MCP is not built. Computer Vision
and Voice (pages 8/9 in reading order) are separate product lines, not part of
this codebase — they should read as connectors/roadmap, not as shipping core.

---

## NEW SLIDE — Access & Roles

**Insert after:** p4 (Vision), before p5 (Architecture) — establishes "who can
do what" before showing the technical flow.

```
A C C E S S   C O N T R O L
สิทธิ์การใช้งานตามบทบาท

ทุกคนใช้แอปเดียวกัน แต่เห็นและทำได้ต่างกันตามบทบาท

01  6 ระดับสิทธิ์ + Admin
    L1–L6 กำหนดว่าแต่ละคนเรียก Model ไหนได้บ้าง ตั้งแต่ Local
    ล้วนไปจนถึง Cloud Model ระดับสูง

02  สิทธิ์เพิ่มตามแผนก
    แผนกได้สิทธิ์เสริมทับบทบาทเดิม เช่น Marketing L2 ใช้
    Gemini Image ได้ ทั้งที่ L2 เดี่ยวๆ ยังไม่ปลดล็อก

03  เปลี่ยนสิทธิ์มีผลทันที
    ปรับบทบาทจาก Admin Console แล้วมีผลกับคำขอถัดไปทันที
    ไม่ต้อง deploy ใหม่

04  งบ Token ต่อบทบาท
    แต่ละบทบาทมีเพดานการใช้ Cloud Model ต่อเดือน ควบคุม
    ต้นทุนได้ตั้งแต่ระดับสิทธิ์

การเข้าถึง Model ทุกตัวผ่านการตรวจสิทธิ์ก่อนเสมอ — ไม่มีทางลัดข้ามระบบสิทธิ์
```

---

## NEW SLIDE — Automatic Data Classification

**Insert after:** the new Access & Roles slide, before p5 (Architecture) — this
is the mechanism that makes "PII ไม่ออกไปหา LLM สาธารณะ" (p2) true.

```
D A T A   C L A S S I F I C A T I O N
จำ แนกชั้นข้อมูลอัตโนมัติ

ระบบอ่านทุกข้อความก่อนตัดสินใจว่าควรไปที่ไหน — ไม่ต้องพึ่งผู้ใช้ติดป้ายเอง

Tier 1–2 · ข้อมูลทั่วไป
เรียก Model ใดก็ได้ตามสิทธิ์ผู้ใช้ ไม่มีข้อจำกัดพิเศษ

Tier 3 · ข้อมูลอ่อนไหว
ลดระดับไปใช้ Local Model อัตโนมัติ พร้อมแจ้งเตือนในหน้าแชท

Tier 4 · ข้อมูลลับสูงสุด
ประมวลผลบน Local เท่านั้น เฉพาะบทบาท L5 ขึ้นไป

ทุกการลดระดับถูกบันทึกลง Audit Log — ไม่ใช่แค่บล็อกเงียบๆ

"ทุกข้อความถูกจัดชั้น จัดเส้นทาง และเข้ารหัสก่อนบันทึกเสมอ"
```

*(Quote line reuses the product's own demo tagline — ties this slide to what's
already shown on the Demo slide, p20.)*

---

## NEW SLIDE — The Policy Engine

**Insert after:** p5 (Architecture) — names the box that Architecture only
implies ("Frontend + Orchestrator: ตรวจสิทธิ์ จัดเส้นทาง").

```
P O L I C Y   E N G I N E
สมองกลางด้านสิทธิ์และความปลอดภัย

ทุกคำขอ ไม่ว่าจะไปที่ Local หรือ Cloud Model ต้องผ่านจุดเดียวนี้เสมอ

จัดชั้นข้อมูล → ตรวจสิทธิ์ผู้ใช้ → ตรวจงบ Token → ตัดสินใจเส้นทาง → บันทึก Audit

ไม่มีช่องทางเรียก LLM ใดๆ ในระบบที่ข้าม Policy Engine ได้
ทุกการตัดสินใจ — อนุมัติ ลดระดับ หรือปฏิเสธ — มีเหตุผลและถูกบันทึกเสมอ

CH-AI Gateway 5b
```

---

## NEW SLIDE — 4-eyes Reveal (Break-glass)

**Insert after:** p11 (Enterprise Data + Governance) — extends the governance
story from "prevent leaks" to "controlled access when access is genuinely
needed."

```
G O V E R N A N C E
เปิดอ่านข้อความแบบ 4-eyes

ข้อความถูกเข้ารหัสเสมอ — แม้แต่ Admin ก็เปิดอ่านคนเดียวไม่ได้

ขอเปิดอ่าน
ระบุเหตุผล ผูกกับข้อความที่ต้องการ

อนุมัติโดยคนละคน
ผู้ขอกับผู้อนุมัติต้องเป็นคนละคนเสมอ (บังคับที่ระดับฐานข้อมูล)

เปิดอ่านแบบมีเวลาจำกัด
อนุมัติแล้วเปิดดูได้ภายใน 24 ชั่วโมง

แจ้งเจ้าของข้อความ
เจ้าของข้อความได้รับแจ้งว่าถูกเปิดอ่าน — ไม่มีการดูแบบเงียบ

จำกัดจำนวนต่อเดือนต่อ Admin ป้องกันการเปิดอ่านพร่ำเพรื่อ ทุกขั้นตอนถูกบันทึกลง Audit Log
```

---

## NEW SLIDE — Cost Governance (per-role budget)

**Insert after:** p14 (Cost Optimization) — that slide is about *speed/latency*
techniques; this one is about *spend control as a governance lever*, which is
a different buyer conversation (finance/compliance, not engineering).

```
C O S T   C O N T R O L
งบ Token ต่อบทบาท ไม่ใช่แค่เทคนิคลดต้นทุน

องค์กรกำหนดเพดานได้เอง ไม่ใช่ปล่อยให้ Cloud API รันจนสิ้นเดือนแล้วค่อยรู้ตัว

งบต่อบทบาท
แต่ละ Role มีโควตา Cloud Model ต่อเดือน รีเซ็ตอัตโนมัติ

เห็นการใช้งานแบบเรียลไทม์
มิเตอร์แสดงโควตาคงเหลือในหน้าแชททุกครั้ง

แดชบอร์ดต้นทุนรายแผนก/รายคน
Admin เห็นผู้ใช้ Cloud Model สูงสุด และค่าใช้จ่ายสะสม

เกินโควตา → ลดระดับ ไม่ใช่หยุดทำงาน
พนักงานยังใช้งาน Local Model ต่อได้เสมอ แม้โควตา Cloud หมด
```

---

## NEW SLIDE — The Platform (app surface)

**Insert after:** p13 (Use Cases) — the demo screenshot (p20) shows a much
richer app (Knowledge base, AI Studio, Library, AI Agent) than any slide
describes; this slide closes that gap.

```
P R O D U C T
ครบในแอปเดียว

Chat
สนทนา ถามตอบ ค้นความรู้ ทำงานแทนได้ในหน้าต่างเดียว

Knowledge base
จัดการคลังเอกสารองค์กร อัปโหลด ติดตาม สถานะประมวลผล

AI Studio
สร้างภาพ/วิดีโอ/เสียงเพลงประกอบงาน ในที่เดียวกับที่แชท

Library
รวมผลงานและไฟล์ที่สร้างไว้ ค้นย้อนหลังได้ง่าย

AI Agent
ประกอบ Agent เฉพาะงานได้เอง ไม่ต้องเขียนโค้ด

Admin Console
สิทธิ์ผู้ใช้ Audit log คำขอเปิดอ่าน แดชบอร์ดต้นทุน ในที่เดียว

พนักงานไม่ต้องสลับแอประหว่างงานความรู้ งานสร้างสรรค์ และงานตรวจสอบ
```

---

## NEW SLIDE — Integrations & Ecosystem

**Insert after:** the new Cost Governance slide (replaces the implicit
"ต่อ CRM/ERP ผ่าน MCP" claim on p2/p4/p12 with an accurate, still-ambitious
picture). This is the slide that fixes the MCP accuracy risk.

```
I N T E G R A T I O N S
เชื่อมกับระบบที่มีอยู่แล้ว

พร้อมใช้วันนี้
✓ Google Workspace SSO — ล็อกอินด้วยบัญชีองค์กรเดิม
✓ OpenAI-compatible API (/v1) — เสียบแทน Cloud LLM เดิมในเครื่องมือที่มีอยู่
  ได้ทันที (เช่น n8n, ระบบ automation อื่นที่รองรับ OpenAI API)
✓ n8n Webhook — สั่งงาน Workflow อัตโนมัติจาก Gateway ได้โดยตรง
✓ CH-Drive — จัดเก็บและดึงเนื้อหาเอกสารสำหรับ RAG

กำลังพัฒนา (Roadmap)
◐ MCP Connector — มาตรฐานเปิดสำหรับต่อ Tool/DB ใหม่แบบปลั๊กอิน
◐ CH-STT — Voice Intelligence เป็น Connector แยก เชื่อมต่อ CH-AI Gateway
◐ Computer Vision (YOLO11 + BoT-SORT) — ผลิตภัณฑ์แยก เชื่อมต่อผ่าน Connector

รายการ "พร้อมใช้วันนี้" คือสิ่งที่ทดสอบและใช้งานจริงแล้ว รายการ Roadmap
คือทิศทางที่วางแผนไว้ ยังไม่ใช่ของที่ส่งมอบได้ทันที
```

---

## NEW SLIDE — Minimum Server Spec (License Tier)

**Insert after:** p18 (Deployment), before the new Commercial/Engagement
slide — gives the concrete hardware numbers behind the deployment tiers p18
already names, so the pricing slide that follows has something to point at.

```
S E R V E R   S P E C
สเปกเซิร์ฟเวอร์ขั้นต่ำ ตาม License Tier

เลือกขนาดโครงสร้างพื้นฐานให้ตรงกับจำนวนผู้ใช้งานจริงขององค์กร

Standard — ไม่เกิน 200 ผู้ใช้
CPU 4c/8T · RAM 16 GB · Storage 500 GB SSD (App+DB เครื่องเดียว)

Professional — ไม่เกิน 500 ผู้ใช้
CPU 8c/16T · RAM 32 GB · Storage 2 TB NVMe/SAN (แยก App และ DB คนละเครื่อง)

Enterprise — ไม่จำกัดจำนวนผู้ใช้
CPU 16c/32T · RAM 64 GB · Storage 5 TB+ NVMe/SAN (แยก App/DB, DR แบบ Hot Standby)

ทุก Tier มาพร้อม DR Server แยกต่างหาก · GPU/Inference Node เลือกได้ตามรูปแบบ
Deployment ที่เลือก (On-premise / Hybrid / Cloud GPU)
```

*(Full sizing assumptions, GPU/inference sizing, data-storage math, and which
of these numbers are commercial packaging vs. engineering-verified today —
including caveats on the App/DB split, K8s, and Hot Standby at Enterprise —
live in `docs/deck/server-spec.md`. That doc should be read before this slide
goes in front of a technically literate customer.)*

---

## NEW SLIDE — Commercial / Engagement Model

**Insert after:** p18 (Deployment) — deployment tiers already exist; this adds
how the engagement itself is packaged/priced.

```
E N G A G E M E N T
รูปแบบการส่งมอบและการลงทุน

Core License
ค่าใช้สิทธิ์ใช้งาน Core (RAG, Primary Brain, Agentic Layer, Security baseline)
ครั้งเดียวหรือรายปี ตามรูปแบบ Deployment ที่เลือก

Connector (ตามขอบเขตงาน)
พัฒนาตามข้อตกลง (SOW) แยกราคาตามความซับซ้อน เช่น จำนวนระบบที่เชื่อม
ปริมาณ Corpus ที่ ingest หรือ Branding เฉพาะองค์กร

Infrastructure
เลือกได้ตาม Deployment: ลงทุน GPU เอง (On-premise) แชร์ต้นทุนแบบ Hybrid
หรือจ่ายตามการใช้งานผ่าน Cloud GPU

ทีมช่วยประเมินขนาดและงบประมาณจริงในขั้น Discovery & Sizing (P0)
ก่อนเริ่มโครงการเสมอ
```

---

## NEW SLIDE — Support & Handover

**Insert after:** the new Engagement slide, before Roadmap (p19) — Roadmap ends
at P4 "ส่งมอบระบบ"; this slide answers "then what."

```
S U P P O R T   &   H A N D O V E R
ดูแลต่อเนื่องหลังส่งมอบ

อบรมผู้ใช้และผู้ดูแลระบบ
ทั้งผู้ใช้ทั่วไปและทีม Admin ก่อนเปิดใช้งานจริง

เอกสารส่งมอบครบชุด
สถาปัตยกรรม การตั้งค่า และคู่มือแก้ปัญหาเบื้องต้น

ช่องทางสนับสนุนหลังส่งมอบ
แจ้งปัญหาและขอความช่วยเหลือได้ตามระดับ SLA ที่ตกลงกัน

ทางเลือก Managed Service
ทีมงานดูแลระบบให้ต่อเนื่องสำหรับองค์กรที่ไม่มีทีม Infra ของตัวเอง
```

---

## NEW SLIDE — Closing / Call to Action

**Insert as:** the new final slide, after p20 (Demo) — the deck currently ends
on a screenshot with no next step.

```
N E X T   S T E P S
พร้อมเริ่มต้นกับ CH-AI Gateway

01. นัดคุย Discovery — สำรวจคลังข้อมูลและความต้องการเบื้องต้น (ฟรี)
02. รับข้อเสนอ Sizing — ประเมินโครงสร้างพื้นฐานและระยะเวลา
03. เริ่ม Pilot — เห็นผลจริงก่อนตัดสินใจลงทุนเต็มรูปแบบ

CODEHARD CO., LTD.
[ชื่อผู้ติดต่อ] · [อีเมล] · [เบอร์โทร]
```

---

## Edits to existing slides

### p2 — Executive Summary
Add a 5th point (or fold into point 01) so the top-of-deck promise matches the
depth shown later:

```
05  ควบคุมและตรวจสอบได้ทุกขั้นตอน
    กำหนดสิทธิ์ตามบทบาท จำแนกชั้นข้อมูลอัตโนมัติ และเปิดอ่านข้อมูล
    ได้เฉพาะกรณีที่มีการอนุมัติแบบ 4-eyes เท่านั้น
```

Also in point 04, replace "ต่อ CRM/ERP และระบบอื่นผ่าน MCP connector" with:

```
ต่อ CRM/ERP และระบบอื่นผ่าน OpenAI-compatible API หรือ MCP connector (roadmap)
เพิ่ม tool/worker ใหม่ได้ง่าย
```

### p4 — Vision
Add a 5th icon+label row alongside รู้/ทำ/ปลอดภัย/ขยาย:

```
ควบคุม
กำหนดสิทธิ์ตามบทบาท จัดชั้นข้อมูลอัตโนมัติ ตรวจสอบย้อนหลังได้ทุกครั้ง
```

### p11 — Enterprise Data + Governance
Add two cards to the existing 4 (PII Filtering / Row-Level Security / Secrets
Vault / Audit Log) — or point to the new dedicated slides instead of expanding
this one:

```
Role-Based Model Access
สิทธิ์เรียก Model กำหนดตามบทบาท (L1–L6) และแผนก ปรับเปลี่ยนได้ทันที

4-eyes Reveal
เปิดอ่านข้อความที่เข้ารหัสไว้ ต้องมีผู้อนุมัติคนละคนกับผู้ขอเสมอ
```

### p5 — Architecture
Rename the "Frontend + Orchestrator / รับคำถาม ตรวจสิทธิ์ จัดเส้นทาง" box
label to explicitly name the engine:

```
Frontend + Orchestrator
รับคำถาม → Policy Engine ตรวจสิทธิ์และจัดชั้นข้อมูล → จัดเส้นทาง
```

### p12 (Delivery Model) — CORE / CONNECTOR list
Under CONNECTOR, change:

```
MCP connector เข้าระบบลูกค้า (CRM/ERP/DB)
```
to:
```
OpenAI-compatible API / n8n — เชื่อมระบบลูกค้าได้ทันที
MCP connector (roadmap) — เข้าระบบลูกค้า (CRM/ERP/DB) แบบมาตรฐานเปิด
```

### Computer Vision (p8 in reading order) & Voice Intelligence (p9)
Add a small eyebrow tag under the section label on both slides:

```
CONNECTOR · ผลิตภัณฑ์แยก เชื่อมต่อกับ CH-AI Gateway
```

This keeps both slides in the deck (they're good vision-building content) while
being explicit that they are not part of the Core being reviewed/priced here.

### p17 — Case Study
Add 3 quantified metric chips below the existing 3 text chips (replace
placeholders with real figures once available; mark clearly if still
placeholder when the deck ships):

```
[ตัวเลขจริงเมื่อพร้อม] ลดเวลาค้นหาข้อมูลลูกค้าลง __%
[ตัวเลขจริงเมื่อพร้อม] ลดต้นทุนเทียบ Public AI ลง __%
[ตัวเลขจริงเมื่อพร้อม] ลดการใช้ Token ด้วย Tokenizer ภาษาไทยลง __%
```

### Model naming (wherever a model is named generically)
Where the deck says "Local Model" without specifics (p2 pt.03, p16), optionally
add the real default in smaller text: `(ค่าเริ่มต้น: Qwen 2.5 14B + BGE-M3
embedding)` — only if the sales team wants to substantiate the claim under
technical questioning; omit if genericizing is intentional for future model
swaps.

### Footer page numbers
Current PDF page numbers repeat/jump (…7, 8, 9, 9, 10, 11, 11, 12, 12, 13, 14,
14…) because slides were reordered without renumbering. Renumber sequentially
1–[N] once the new slides above are inserted.
