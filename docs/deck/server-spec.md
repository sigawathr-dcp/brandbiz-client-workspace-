# Minimum Server Spec — CH-AI Gateway

**Insert after:** deck p18 (Deployment) — p18 names the three deployment models
(On-premise / Hybrid / Cloud GPU); this doc gives the hardware numbers behind them,
in the same slide-table shape used elsewhere in this deck.

All figures below are sized against the stated target in `PLAN.md` §1: **~100 employees,
peak ~15 simultaneous chats, Thai + English**. §1 sizing assumptions explains every number;
don't copy the tables out of context.

---

## 1. สมมติฐานการประเมิน (Sizing assumptions)

| Assumption | ค่า | ที่มา |
|---|---|---|
| จำนวนผู้ใช้ | ~100 employees | `PLAN.md` §1 (line 33) |
| Concurrency สูงสุด | ~15 simultaneous chats | `PLAN.md` §1 (line 35) |
| เป้าหมาย load test | 30 concurrent, p95 < 5 s | 30 concurrent: `PLAN.md` §9; Task 3.7 — p95 < 5s: `PLAN.md:336` (§6 Phase 1 gate; §9/Task 3.7 themselves state only the concurrency figure, not the latency threshold) |
| การใช้งานต่อคน (สมมติ) | ~10 requests/day | ตัวเลขสมมติจาก client proposal, `PROGRESS.md` 2026-06-23 |
| Corpus เริ่มต้น (สมมติ) | 5 GB เอกสารต้นฉบับ | baseline — ดูสูตรขยายผลใน §4 |
| Retention | **ไม่มีการลบอัตโนมัติ** (ลบมือได้บางส่วน) | ดูหมายเหตุด้านล่าง |
| Operational reserve | **15%** ของดิสก์ ไม่จัดสรรให้ใคร | §7 — Postgres เสื่อมหนักเมื่อ >90%, `pg_repack` ต้องมีที่ว่าง |

**หมายเหตุเรื่อง License Tier (§2):** หลักฐาน sizing ทั้งหมดข้างต้นอิงกับเป้าหมายจริงของโปรเจกต์
คือ ~100 employees / ~15 concurrent (`PLAN.md` §1) — ไม่ใช่ 200/500/unlimited users
ตัวเลข ≤200 / ≤500 / Unlimited ในตารางที่ 1 (§2) เป็น **commercial packaging** ที่ทีมขายกำหนด
ไม่ใช่ตัวเลข capacity ที่วัดหรือทดสอบจริงกับระบบนี้ — ดู §5 สำหรับ ladder ที่อิงหลักฐานจริง

> **หมายเหตุสำคัญ:** `PLAN.md` D14 กำหนด retention ของ `messages.content_*` ไว้ 30 วัน แต่ในระบบที่ deploy จริง
> ไม่มี purge job ใดๆ (`backend/app/workers/__init__.py` เป็นไฟล์ว่าง — ไม่มี Celery, ไม่มี beat, ไม่มี pg_cron,
> ไม่มี APScheduler) และ `audit_log` ก็ไม่ได้ partition (migration `0003_audit_partitions` ถูกลบออกโดย commit
> ที่ตัดเข้าสู่ demo mode) **ตัวเลข Data Storage ใน §2 จึงเป็นตัวเลขสะสม (cumulative) ไม่ใช่ steady-state**
>
> สถานะการลบ/จำกัดพื้นที่ที่แท้จริง (ตรวจจากโค้ด 2026-08-06):
>
> | ความสามารถ | สถานะ | หลักฐาน |
> |---|---|---|
> | ลบไฟล์ corpus (ลบ chunks + blob + row) | ✅ **มีแล้ว** | `backend/app/routers/files.py:274-289` |
> | ลบ agent / skill / API key | ✅ มีแล้ว | `agents.py:227`, `skills.py:226`, `admin.py:1082` |
> | ลบ conversation / message | ❌ ไม่มี route | ไม่มี `@router.delete` ใน `conversations.py`, `chat.py` |
> | ลบ Studio generation | ❌ ไม่มี route | ไม่มี `@router.delete` ใน `studio.py` |
> | Quota | ⚠️ **เป็น token/cost quota ไม่ใช่ storage** | `services/quota.py` — docstring: *"consumed ONLY for external API calls"* → chat ผ่านโมเดล local **ไม่กิน quota เลย** และ image gen จริงก็ไม่ถูก gate (`models/studio.py:58`) |
> | Retention job / scheduler | ❌ ไม่มีทั้งระบบ | `backend/app/workers/__init__.py` ว่างเปล่า |
>
> ⇒ งานที่เหลือเพื่อไปสู่ตัวเลขแบบ steady-state ใน §7 คือ **storage quota + scheduler + ปุ่มลบอีก 2 จุด**
> ไม่ใช่เริ่มจากศูนย์

---

## 2. ตารางที่ 1 — Minimum Server Spec แยกตาม License Tier

*(GPU/Inference แยกไปอยู่ตารางที่ 2 เสมอ — ทุก tier ด้านล่างต้องมี inference node แยกต่างหาก
ตามรูปแบบ deployment ที่เลือก (On-premise / Hybrid / Cloud GPU — แกนนี้ไม่ได้หายไป เป็นแกน
**orthogonal** กับ license tier ด้านล่าง ดู deck p18 และหมายเหตุท้ายไฟล์)*

| Tier | Users | CPU | RAM / OS Storage | Data Storage (3-year cumulative, incl. AI Studio) |
|---|---|---|---|---|
| **Standard** | 200 | 8c/16T | 32 GB / 100 GB | 500 GB |
| **Professional** | 500 | 16c/32T | 64 GB / 100 GB | 1 TB |
| **Enterprise** | 1000 | 24–32c / 48–64T | 128 GB / 100 GB | 1.5 TB |

**หมายเหตุ (สิ่งที่ตารางนี้ "สมมติไว้" แต่ยังไม่มีในโค้ดจริงวันนี้):**

ตัวเลขข้างบนคงไว้ตรงตามที่ทีมขายส่งมา (verbatim) เพื่อให้วางลง deck ได้ทันที ฝั่ง CPU/RAM ปรับขึ้นมาดีขึ้น
ชัดเจนจากเวอร์ชันก่อน (Standard ขยับจาก 4c/16 GB → 8c/32 GB = ตรงกับ ladder ที่อิงหลักฐานจริงใน §5 แล้ว)
แต่ต้องอ่านคู่กับช่องว่าง 6 ข้อนี้ก่อนรับปากลูกค้า:

1. **ไม่มี GPU / VRAM ในตารางเลย — เป็นช่องว่างที่แพงที่สุด** ตารางนี้ครอบคลุมเฉพาะ App+DB ระบบต้องมี
   **inference node แยกเสมอ** (ตารางที่ 2, §3) ซึ่งราคาสูงกว่าเครื่องในตารางนี้หลายเท่า ถ้าถือ concurrency
   ≈ 10% ของ seats: Standard ~20 · Professional ~50 · Enterprise ~100 concurrent → ต้องการ 48 GB ·
   2×48 GB · 4×48 GB (หรือ 2×80 GB) ตามลำดับ ซ้ำร้าย โมเดลที่ deploy จริงคือ `gemma4:26b`
   (`docker-compose.yml:34`) ใหญ่กว่างบ VRAM ~14.5 GB ที่วางแผนไว้ และ multi-instance + load balancer
   (Task 3.7) **ยังไม่ได้ทำ** — ซื้อการ์ดมา 4 ใบวันนี้ซอฟต์แวร์ก็ยังกระจายโหลดไม่ได้
2. **คอลัมน์ "Users" ไม่ได้นิยาม** — 200/500/1000 คือ named seats หรือ concurrent? ถ้าไม่ระบุอัตรา
   concurrency ที่สมมติไว้ ทุกตัวเลขในแถวนั้นตรวจสอบไม่ได้ **ควรเติมคอลัมน์ "Peak concurrent chats"**
   เพราะเป็นตัวแปรเดียวที่กำหนดทั้งขนาด GPU และ DB pool
3. **Data Storage สเกลผิดทิศ** — ต่อผู้ใช้ 1 คน/3 ปี ได้ 2.5 GB (Standard) → 2.0 GB (Professional)
   → **1.5 GB (Enterprise)** คือ *ลดลง* เมื่อ tier ใหญ่ขึ้น ซึ่งจะสมเหตุสมผลก็ต่อเมื่อตัวกินพื้นที่หลักเป็นของกลาง
   ระดับองค์กร แต่ในระบบนี้ตัวกินพื้นที่หลักคือ **AI Studio ซึ่งเป็นรายคน** และเก็บเป็น base64 ใน Postgres
   `TEXT` (`backend/app/services/studio.py:386`) โดยไม่มี storage quota / retention / ปุ่มลบ
   ⇒ ใช้ Studio แบบทีมมาร์เก็ตติ้งจริง (2–3 ชิ้น/คน/วันทำงาน ≈ 3.9 GB/คน/3 ปี) จะทำให้ **Standard เกิน
   500 GB (~780 GB) และ Enterprise เกิน 1.5 TB ไป ~2.6 เท่า (~3.9 TB)** — ดู §7 สำหรับตัวเลขที่ bound ได้
4. **OS Storage 100 GB คือกับดักที่ทำให้ดิสก์เต็มก่อนใช้ครบปี** — `docker-compose.yml:171-175` ใช้
   **named volumes** (`postgres_data`, `files_data`, `vault_data`) ซึ่งโดย default อยู่ใต้
   `/var/lib/docker/volumes` = **บนดิสก์ OS ไม่ใช่ Data Storage** ถ้า commissioning ไม่ bind-mount
   ไปยัง data volume อย่างชัดเจน คอลัมน์ Data Storage ทั้งคอลัมน์จะไม่ถูกใช้เลย
   ⇒ **แนะนำ OS = 200 GB** (Docker images + logs + หัวไหล่) พร้อมระบุเงื่อนไข bind-mount
5. **แถว DR หายไปจากเวอร์ชันก่อน** — ตอนนี้ทุก tier เป็น single point of failure และไม่มีการเผื่อพื้นที่
   backup เลย ทั้งที่เคยเสนอลูกค้าว่า `pg_dump` รายคืน เก็บ 14 วัน / RPO ≤24 ชม. / RTO ≤4 ชม.
   ⇒ **Backup target แยกต่างหาก = 1.5–2× ของ Data Storage** และถ้า DB โตถึงหลักหลายร้อย GB
   โดยมี TEXT ก้อนใหญ่ `pg_dump` จะใช้เวลาเป็นชั่วโมง → **RTO ≤4 ชม. เสี่ยงไม่ผ่าน**
6. **ตัวเลขทั้งหมดเป็นแบบสะสม (cumulative)** ตามที่อธิบายใน §1 ⇒ **§7 คือเวอร์ชันที่ bound ได้**
   (steady-state ceiling) ซึ่งเป็นตัวเลขที่ควรใช้บนสไลด์แทนตารางนี้ เมื่องาน retention/quota เสร็จ

> **สำคัญ:** ความจุจริงวันนี้ของทั้ง 3 tier **เท่ากันเป๊ะ** เพราะเพดานอยู่ที่ configuration ไม่ใช่ hardware
> — ดู §6.1 (DB pool 15 connections → ~7–8 chat พร้อมกัน ทุก tier)

---

## 3. ตารางที่ 2 — GPU / Inference Node

| Workload | Model | Quant | Weights | KV Cache | Peak VRAM | การ์ดที่แนะนำ |
|---|---|---|---|---|---|---|
| Primary brain (ตามแผน, D4) | Qwen2.5-14B-Instruct | Q5_K_M | ~10.2 GB | ~2.7 GB @32K ctx (Q8) | ~13 GB | — |
| + Embeddings | BGE-M3 | Q8 | ~1.2 GB | — | **รวม ~14.5 GB** | **24 GB (เช่น RTX 4090)** |
| **ที่ใช้งานจริงวันนี้** | `gemma4:26b` | ตามที่ deploy | ใหญ่กว่างบ 14.5 GB ข้างต้นอย่างมีนัยสำคัญ | — | สูงกว่าประมาณการแผนเดิม | 24 GB ตึงมือ / **แนะนำ 32–48 GB** |

*(แหล่งอ้างอิง: `README.md:50-53` สำหรับงบ VRAM ตามแผน — หมายเหตุ: `PLAN.md` §8 Gotcha #3
ให้ตัวเลข KV cache ที่ต่างกัน (~6 GB แทน ~2.7 GB ข้างต้น รวมแล้ว ~17.2 GB ไม่ใช่ ~14.5 GB) ยังไม่มีการ
verify จริงว่าตัวเลขไหนถูก — ดูตารางที่ 2 แถวสุดท้ายสำหรับสถานะจริง; `.env:32-33` และ
`docker-compose.yml:33-34` สำหรับโมเดลที่ deploy จริงคือ `gemma4:26b` บนเครื่อง Ollama แยก
ที่ `192.168.20.18:12341` — คนละตัวกับ `backend/app/config.py:69` ซึ่งเป็น `hermes_ollama_model`
ของ Hermes เอง (port `12342`, ใช้เฉพาะ render host-setup script) และคนละตัวกับ default ใน
`config.py:30` ที่ยังเขียนว่า `qwen2.5-14b-local` — ความต่างนี้เองคือหลักฐานว่าระบบที่ deploy จริง
เบี่ยงไปจากที่ตั้งค่า default ไว้)*

### Concurrency ladder

| ผู้ใช้พร้อมกัน (concurrent) | GPU ที่ต้องการ | หมายเหตุ |
|---|---|---|
| ≤4 concurrent | 24 GB (1 การ์ด) | `llama.cpp --parallel 4` คือค่าที่ทดสอบแล้วบน RTX 4090 — ไปที่ 8 เสี่ยง OOM (`PLAN.md` §8) |
| ~15 concurrent (เป้าหมายจริงของระบบ) | 48 GB หรือ 2×24 GB + load balancer | ต้องทำ Task 3.7 (multi-instance llama.cpp + load balancer) ซึ่ง**ยังไม่ได้ทำ** ในโค้ดปัจจุบัน |
| 30+ concurrent (เป้าหมาย load test) | 2×48 GB หรือ 80 GB ×1 | ยังไม่เคยทดสอบจริงบน GPU (ดู §6) |

### ข้อควรระวัง (GPU caveats)

- **`LLM_KEEP_ALIVE=0`** (`backend/app/config.py:35-38`) — โมเดลถูก unload ออกจาก VRAM ทุกครั้งหลัง request
  เพื่อให้โมเดล chat และ embedding แชร์ GPU ตัวเดียวกันได้ ผลคือมี **reload penalty ทุก request**
  ทางแก้คือเพิ่ม VRAM ให้ทั้งสองโมเดลอยู่ค้างพร้อมกันได้ หรือแยกการ์ด
- **`ollama pull bge-m3` อาจยังไม่เคยรันบนเครื่อง inference จริง** (`production_improvement.md` gap #3)
  — ควรตรวจสอบก่อนรับปากความสามารถ RAG ใดๆ กับลูกค้า

---

## 4. ตารางที่ 3 — Data Storage Breakdown

| องค์ประกอบ | ที่เก็บ | ขนาดต่อหน่วย | อัตราการโต | หมายเหตุ |
|---|---|---|---|---|
| `messages` (เข้ารหัส) | Postgres `BYTEA` | plaintext bytes + 28 B/field, **ไม่บีบอัด** (AES-GCM ciphertext) | 2 rows/ครั้งสนทนา | TOAST เก็บแบบ external, uncompressed |
| `audit_log` | Postgres, `JSONB` + 2 index | ~300 B – 1.5 KB/แถว | 1–4 rows/ครั้งสนทนา (73 call sites) | **ไม่เคย purge, ไม่ได้ partition** |
| `file_chunks` | Postgres, `VECTOR(1024)` + HNSW index | ~10–12 KB/chunk (vector 4,104 B + text + สำเนาใน index) | `ceil(chars ÷ 1800)` chunks ต่อเอกสาร | chunk 500 tokens, overlap 50 tokens, ~4 chars/token (`config.py:46-49`) |
| ไฟล์ต้นฉบับ (blob) | Local disk `/data/files` | ≤50 MB/ไฟล์ (`config.py:51`) | ต่อการอัปโหลด | **ไม่มี quota รวมทั้งองค์กร** |
| `studio_generations` | **Postgres `TEXT` (base64 data URL)** | รูป 1.4–2.7 MB · วิดีโอ 8 วิ 1.3–8 MB · เพลง 30 วิ ~0.6 MB | ต่อการสร้างหนึ่งครั้ง | **ไม่มี quota, ไม่มี token cost, ไม่มี retention** |
| Obsidian vault sync | Disk ×2 + Postgres | git clone (พร้อม history เต็ม, `backend/app/services/vault_runner.py:72` — ไม่มี `--depth`) + สำเนาซ้ำใน `/data/files` + chunks | ต่อ note | `backend/app/services/vault_sync.py:131-153` |
| Backup | ปลายทางแยก | `pg_dump` รายคืน × เก็บ 14 วัน | — | Phase 4, **ยังไม่ได้ implement** |

### ตัวอย่างการคำนวณ

- Chat + audit: ~100 users × ~220 turns/เดือน (จาก 10 req/day) ≈ **~1.1 MB/user/เดือน** ≈ **~1.3 GB/ปี ทั้งองค์กร**
  → ส่วนนี้เล็กมาก ไม่ใช่ตัวขับเคลื่อนหลัก (ตัวเลข 10 req/day มาจาก `PROGRESS.md` 2026-06-23 17:00
  ซึ่ง sized ไว้สำหรับ **~30 users** ไม่ใช่ 100 — การขยายผลมาที่ 100 users ในบรรทัดนี้เป็นการต่อยอด
  สมมติฐานเดิม 3.3 เท่า ไม่ใช่ตัวเลขที่วัดที่ 100 users โดยตรง)
- Corpus/RAG: เอกสาร 1 GB (ข้อความล้วน) → ~583 chunks/MB (stride 1,800 ตัวอักษร, `ingestion.py:184`)
  → **ประมาณ 7 GB ใน Postgres ต่อ 1 GB corpus** (text + vector + HNSW index รวมกัน; คำนวณละเอียด
  ได้ ~6.3 GB — ปัดขึ้นเป็น ~7 GB)
- Studio media: การสร้างภาพ/วิดีโอ/เพลงแต่ละครั้งกิน 0.6–8 MB ต่อครั้ง สะสมได้หลัก **GB/ปี** ได้ง่ายถ้าใช้งานสม่ำเสมอ
  เพราะไม่มีการจำกัดหรือลบทิ้ง

**สรุป:** ตัวขับเคลื่อนพื้นที่เก็บข้อมูลหลักคือ **corpus ที่ ingest เข้า RAG และ media ที่สร้างจาก Studio**
ไม่ใช่ข้อความแชทเอง — ตัวเลข Data Storage ในตารางที่ 1 (§2) ของทุก license tier เผื่อสองส่วนนี้เป็นหลัก
(และตามที่ระบุใน §2 ข้อ 3 ตัวเลขในตารางที่ 1 ควรอ่านเป็น **พื้นล่าง (floor) ไม่ใช่เพดาน** ตราบใดที่ยังไม่มี
storage quota — เวอร์ชันที่เป็นเพดานจริงอยู่ใน §7)

---

## 5. ตารางที่ 4 — Scale Steps (Engineering-evidence ladder)

*หมายเหตุ: ตารางนี้คือ "commercial ladder" คนละอันกับตารางที่ 1 (§2, License Tier) — ตัวเลขที่นี่
อิงหลักฐานที่วัด/ทดสอบจริงกับระบบ (`PLAN.md` §1, §9) ในขณะที่ §2 คือ commercial packaging
ของทีมขาย เกณฑ์ผู้ใช้จึงไม่ตรงกัน (Pilot ≤50 / Production ~100 / Scale 300+ ที่นี่ เทียบกับ
Standard 200 / Professional 500 / Enterprise 1000 ใน §2) — ใช้ตารางนี้เมื่อต้องอ้างอิงหลักฐาน engineering จริง
ใช้ §2 เมื่อต้องอ้างอิง commercial packaging*

| ระดับ | CPU | RAM | Data Storage | หมายเหตุ |
|---|---|---|---|---|
| Pilot (≤50 users) | 4c/8T | 16 GB | 500 GB | เหมาะสำหรับทดสอบก่อนเปิดใช้งานเต็มรูปแบบ |
| Production (~100 users, เป้าหมายปัจจุบัน) | 8c/16T | 32 GB | 1 TB | = baseline เดิมก่อนแยกตาม license tier |
| Scale (300+ users หรือ corpus ขนาดใหญ่) | 16c/32T | 64 GB | 2 TB+ | แนะนำแยก App และ DB คนละเครื่อง |

---

## 6. ข้อจำกัดที่มีผลต่อการ Sizing (ต้องแจ้งลูกค้าให้ชัดเจน)

- **API tier ยัง scale แนวนอน (horizontal) ไม่ได้ในปัจจุบัน** — rate limiting เป็น in-process dict
  (`backend/app/services/rate_limit.py`, docstring ของไฟล์เตือนเรื่อง unbounded growth เอง) และงาน background
  ทั้งหมด (file ingestion, studio video, agent tasks, vault sync) รันผ่าน FastAPI `BackgroundTasks`
  ในโปรเซส API เดียว — เพิ่ม replica ที่สองจะไม่ share state ใดๆ เลย ตอนนี้จึง **scale ได้แนวตั้ง (vertical) เท่านั้น**
- **การ restart API จะทำให้ background task ที่ค้างอยู่หายไป** (ค้างสถานะ `running`) — ตามที่ระบุไว้ใน
  `PLAN.md` Task 3.12 (ทราบปัญหาแล้ว แต่ยังไม่แก้)
- **Redis / Object storage (S3) / Message queue / Reverse proxy ไม่ได้ deploy อยู่จริง** — `docker-compose.yml`
  มีเพียง `postgres`, `backend-api`, `frontend-chat` (+ `hermes` / `hermes-init` แบบ opt-in) เท่านั้น หาก deployment mode ใด
  สัญญาว่ามี S3 หรือ queue-backed workers ให้ถือว่าเป็นงานพัฒนาเพิ่มเติม ไม่ใช่แค่ config
- **ไม่มี HA, ไม่มี replication, ไม่มี failover จริง** — ตารางที่ 1 (§2) เวอร์ชันปัจจุบัน **ตัดแถว DR ออกไปแล้ว**
  ซึ่งตรงกับความจริงมากกว่าเวอร์ชันก่อน (ที่เคยเขียนว่า "DR Warm/Hot Standby") แต่แปลว่าทุก tier เป็น
  single point of failure และ DR ที่มีจริงคือ *restore จาก `pg_dump`* เท่านั้น — ไม่ใช่ hot standby /
  streaming replication ระบบยังไม่มี Postgres replica เลยไม่ว่าแบบ warm หรือ hot
- **ตัวเลข Backup/DR ที่เคยเสนอลูกค้า**: `pg_dump` รายคืน / เก็บ 14 วัน, **RPO ≤24 ชม., RTO ≤4 ชม.**,
  ทดสอบ restore ทุกไตรมาส, SLA 99.5% (`PROGRESS.md` 2026-06-23 17:00) — ตัวเลขเหล่านี้เป็น **เป้าหมายตามสัญญา
  ไม่ใช่สิ่งที่ implement แล้ว** (`production_improvement.md` gap #10: "No backups")
- **ยังไม่เคย load test บน GPU จริง** (`production_improvement.md` gap #15) — ตัวเลข latency/concurrency
  ทั้งหมดในเอกสารนี้เป็น **เป้าหมาย ไม่ใช่ผลวัดจริง**
- **ไม่มี K8s manifest ใดๆ ในโค้ดนี้** — deploy เป็น single-VM Docker Compose เท่านั้น (`docker-compose.yml`
  + `docker-compose.altports.yml` / `docker-compose.noports.yml`) ตารางที่ 1 เวอร์ชันปัจจุบันไม่มีคอลัมน์
  OS/Platform แล้ว จึงไม่ได้อ้าง K8s อีก — แต่ถ้าจะใส่กลับเข้าไปใน deck ต้องถือเป็นเป้าหมายเชิงพาณิชย์
  ไม่ใช่สิ่งที่ implement แล้ว
- **Enterprise 1000 users เป็นตัวเลขที่ซอฟต์แวร์รับไม่ได้วันนี้** ไม่ว่าฮาร์ดแวร์จะแรงแค่ไหน — CPU 24–32c
  ในตารางที่ 1 ใช้ไม่ได้จริงเพราะ API รันเป็น **โปรเซสเดียว** (`--reload` override `--workers 4`,
  `docker-compose.yml:22`) และการเพิ่ม worker/replica ต้อง **แก้โค้ด** ก่อน (rate limit เป็น in-process dict,
  background task อยู่ในโปรเซส uvicorn) ดู §6.1

### 6.1 เพดานความจุที่แท้จริงอยู่ที่ Configuration ไม่ใช่ Hardware

ตรวจสอบเพิ่มเติม (2026-08-06) พบว่าตัวเลข CPU/RAM ในตารางที่ 1 (§2) **ยังไม่เพียงพอ** สำหรับความจุที่
แต่ละ tier ตั้งใจจะรองรับ — ไม่ใช่เพราะ hardware น้อยไป แต่เพราะยังไม่มี configuration ที่จำเป็นในการ
ใช้ hardware นั้น การเพิ่ม CPU/RAM ในตารางเพียงอย่างเดียว **จะไม่แก้ปัญหาต่อไปนี้เลย**:

- **DB connection pool ยังไม่ได้ตั้งค่า** — `backend/app/db.py:7` สร้าง async engine โดยไม่กำหนด
  `pool_size`/`max_overflow` ค่า default ของ SQLAlchemy คือ 5 + 10 = **15 connections รวมทั้งระบบ**
  การแชทแบบ streaming ถือ connection ไว้นานสุดถึง `llm_read_timeout` 120 วินาที (`config.py:42`)
  ขณะที่การเขียน audit log เปิด connection ที่สองพร้อมกัน (`services/audit.py:36-49`) — ผลคือระบบรองรับ
  ได้จริงเพียง **~7–8 การสนทนาพร้อมกัน** ต่ำกว่าเป้าหมาย ~15 concurrent ใน §1 ด้วยซ้ำ ไม่ว่าจะใช้ tier ไหน
- **Postgres ยังไม่ได้ tune เลย** — `docker-compose.yml` ไม่มี `command:`, ไม่มี config file mount,
  ไม่มี init SQL ใดๆ (`db/init/` มีแค่ README) ค่า default ของ `pgvector/pgvector:pg16` คือ
  `shared_buffers=128MB` เท่านั้น — RAM ในตารางที่ 1 จึงยังใช้เป็น Postgres cache ไม่ได้จริงจนกว่าจะตั้งค่า
- **`--reload` คือคำสั่งที่ deploy จริง** — `docker-compose.yml:22` override คำสั่ง `--workers 4`
  ใน `backend/Dockerfile` ด้วย `--reload` ผลคือมีเพียง 1 worker process (+ filesystem watcher)
  คอลัมน์ CPU ทั้งหมดในตารางที่ 1 จึงยังไม่ได้ถูกใช้ประโยชน์จริงฝั่ง API tier

**ข้อสรุป:** สิ่งเหล่านี้เป็น **งาน configuration ก่อนเปิดใช้งานจริง (commissioning)** ไม่ใช่การซื้อ hardware
เพิ่ม — ควรแจ้งลูกค้าให้ชัดว่าตัวเลขในตารางที่ 1 เป็นจุดเริ่มต้นที่ต้องมาพร้อมงาน tuning เหล่านี้เสมอ
มิฉะนั้น tier ที่ซื้อไปจะไม่ถึงความจุที่ตั้งใจไว้ รายละเอียดทางเทคนิคเพิ่มเติม (Studio gallery, upload
buffering, missing indexes) บันทึกไว้ใน `production_improvement.md` (ไม่ใช่เอกสารนี้ เพราะเป็นราย
ละเอียดระดับวิศวกรรม ไม่ใช่ตัวเลขที่นำเสนอลูกค้าโดยตรง)

---

## 7. Sizing ภายใต้ Retention + Storage Quota (steady-state ceiling)

ทั้งหมดใน §2–§6 อธิบายระบบ **วันนี้** ซึ่งข้อมูลโตแบบไม่มีเพดาน หัวข้อนี้ตอบคนละคำถาม:
*ถ้าทำ retention + storage quota + ปุ่มลบให้ครบ ตัวเลขจะเป็นเท่าไหร่* — และตัวเลขชุดนี้คือชุดที่ควรอยู่บนสไลด์ขาย

**สิ่งที่เปลี่ยนก่อนอื่นคือหัวตาราง:** จาก *"3-year cumulative"* → **"steady-state ceiling"**
เพราะเมื่อมี retention แล้วตัวเลขไม่โตตามเวลาอีก มันนิ่งอยู่ที่เพดาน และเพดานนั้นคือ quota ที่เราตั้งเอง
⇒ เปลี่ยนจาก *"เดาว่าโตแค่ไหน"* เป็น **"เลือกได้ว่าจะให้โตแค่ไหน"**

### 7.1 Policy ที่สมมติ

| รายการ | ค่า | หมายเหตุ |
|---|---|---|
| `messages.content_*` | เก็บ 30 วัน | = D14 ที่ตัดสินใจไว้แล้ว เพียงแต่ยังไม่ implement |
| Studio media | เก็บ 90 วัน | ค่าเสนอ — เป็นลูกบิดที่ปรับได้ |
| `audit_log` | **เก็บถาวร** | ลบไม่ได้ตามกฎโปรเจกต์ (`CLAUDE.md`, PLAN §7.3) → ใช้ partition + detach ไป cold storage แทน |
| Corpus (RAG) | จำกัดด้วย quota ระดับองค์กร | ไม่ใช้ retention — knowledge base ต้องอยู่ถาวร |
| Media quota | ต่อ workspace (pooled) | ดู §7.4 |

### 7.2 สูตร sizing

```
Disk = [ corpus_quota × 8  +  media_pool  +  chat_audit ] × 1.4 × 1.15
              ↑ RAG multiplier    ↑ per-seat    ↑ ลบไม่ได้   ↑ bloat  ↑ reserve
                                                              WAL/temp   15%
```

- **×8** — corpus 1 GB → `file_chunks` ใน Postgres ~7 GB (vector + text + HNSW, §4) + สำเนาไฟล์ต้นฉบับบนดิสก์
- **×1.4** — dead tuple bloat + WAL + temp ตอน reindex (ฟิสิกส์ของ Postgres ไม่ใช่ policy — ลดไม่ได้)
- **×1.15** — **operational reserve ตามที่ร้องขอ**: ดิสก์ไม่เคยถูกจัดสรรเกิน 85% เพราะ Postgres เสื่อมสภาพ
  หนักเมื่อเกิน 90%, autovacuum ต้องมีที่หายใจ และ `pg_repack` ต้องการที่ว่างชั่วคราว
- **chat_audit** ≈ 17 MB/คน/3 ปี (audit ถาวร ~16 MB + chat 30 วัน ~0.7 MB) — อิงสมมติฐาน 10 req/day ใน §1

### 7.3 ตารางที่ 5 — Storage ceiling ต่อ tier (เผื่อ 15% แล้ว)

| Tier | Users | Disk | Corpus quota | Media pool | เฉลี่ย/คน | ว่างสำรอง |
|---|---|---|---|---|---|---|
| **Standard** | 200 | 500 GB | 15 GB | **180 GB** | 0.90 GB | 75 GB (15.0%) |
| **Professional** | 500 | 1 TB | 25 GB | **415 GB** | 0.83 GB | 152 GB (14.8%) |
| **Enterprise** | 1000 | **2 TB** | 60 GB | **750 GB** | 0.75 GB | 302 GB (14.8%) |

**Standard 500 GB และ Professional 1 TB ตามที่ทีมขายกำหนด — ป้องกันได้แล้ว** ✅

**Enterprise 1.5 TB ยังไม่พอ** ❌ ที่ดิสก์ 1.5 TB (งบ logical = 1536 ÷ 1.61 = 954 GB) หัก corpus 480 GB
และ audit 17 GB จะเหลือให้ media เพียง **~455 GB = 0.46 GB/คน (~180 ภาพ)** — ต่ำกว่า Standard ครึ่งหนึ่ง
ซึ่งขายไม่ได้สำหรับ tier แพงสุด และถ้าลูกค้าต้องการ corpus quota 100 GB (สมเหตุสมผลสำหรับองค์กร 1000 คน)
ตัวเลขจะร่วงเหลือ **0.28 GB/คน (~110 ภาพ)** ⇒ ตัวขับพื้นที่หลักของ Enterprise **ไม่ใช่ media แล้ว
แต่เป็น `corpus × 8`** ทางเลือกมี 2 ทาง:

| ทางเลือก | Disk | วิธี |
|---|---|---|
| **(A) ซื้อดิสก์เพิ่ม** | 2 TB | ไม่ต้องแก้โค้ด — ใช้ตัวเลขในตารางข้างบน |
| **(B) แก้สถาปัตยกรรม** | **1.5 TB พอ** | ทำ 2 อย่าง แล้วได้ media pool 780 GB (0.78 GB/คน) เท่ากับทาง (A) |

ทางเลือก (B) ประกอบด้วย:

| งาน | ผลต่อพื้นที่ | ความยาก |
|---|---|---|
| **ย้าย Studio media ออกจาก Postgres ไปดิสก์/S3** | ไม่ต้องเผื่อ bloat 40% (เหลือ ~10% ฝั่ง filesystem) + `unlink()` คืนพื้นที่ทันที + `pg_dump` เร็วขึ้นมาก | กลาง — มี `/data/files` + `delete_blob()` ให้ reuse อยู่แล้ว |
| **เปลี่ยน `VECTOR(1024)` → `halfvec(1024)`** | 4,104 B → 2,056 B ต่อ vector ทั้งในตารางและใน HNSW ⇒ RAG multiplier **×8 → ×5** | ต่ำ — migration + reindex, pgvector รองรับ |

*(คำนวณทาง (B): Postgres = (corpus 60×5 + audit 17) × 1.4 = 444 GB · media บน filesystem = 780 × 1.1
= 858 GB · รวม 1,302 GB จาก 1,536 GB ⇒ เหลือว่าง 234 GB = 15.2%)*

### 7.4 Pooled quota — ตัวเลขที่ขายได้สูงขึ้นโดยไม่ต้องเพิ่มดิสก์

ถ้าตัวนับ (§7.5) นับที่ระดับ **workspace/org** ไม่ใช่ per-user ตายตัว จะ overcommit ได้ เพราะมีเพียง
~20–30% ของ seat ที่ใช้ media หนัก — ฮาร์ดแวร์เท่าเดิมทุกประการ แต่ตัวเลขบนสไลด์ดีขึ้น 5–10 เท่า

| Tier | Disk | per-user ตายตัว | **แบบ pooled (แนะนำ)** |
|---|---|---|---|
| Standard | 500 GB | 0.90 GB/คน | **"สูงสุด 5 GB/คน · พูลรวม 180 GB"** |
| Professional | 1 TB | 0.83 GB/คน | **"สูงสุด 5 GB/คน · พูลรวม 415 GB"** |
| Enterprise | 2 TB (หรือ 1.5 TB ตามทาง B) | 0.75 GB/คน | **"สูงสุด 10 GB/คน · พูลรวม 750 GB"** |

> 1 GB/คน ≈ **400 ภาพ** หรือ **~120 คลิป 8 วินาที** ที่ค้างอยู่พร้อมกัน (เกินแล้วลบตัวเก่าอัตโนมัติ)
> — ตัวเลขที่อธิบายลูกค้ารู้เรื่องและยอมรับได้

### 7.5 ข้อกำหนดของตัวนับ (storage counter)

ตัวเลขทั้งหมดใน §7 เป็นจริงได้ก็ต่อเมื่อ quota **บังคับได้** = ต้องมีตัวนับ ⇒ ตัวนับไม่ใช่ optimization
แต่เป็น **เงื่อนไขที่ทำให้ §7 ทั้งหัวข้อไม่ใช่การเดา** และมีข้อกำหนด 4 ข้อ:

1. **ต้องระบุบนเอกสารสัญญาว่า "quota นับอะไร"** — ตัวนับนับ *logical bytes* แต่ดิสก์คิด *physical bytes*
   และคลาดกันทั้งสองทาง: base64 พองจากไบนารี +33% แต่ TOAST บีบกลับด้วย pglz เกือบหมด
   (⇒ over-count ~33%) ขณะที่ index + WAL + dead tuple bloat ทำให้ under-count (~40%)
   สุทธิใกล้เคียงกันโดยบังเอิญ **แต่อย่าอ้างว่าแม่น** — แนะนำ: นับ logical bytes ของ media + ไฟล์ต้นฉบับ
   แล้วใช้ `1.4×` เป็น calibration factor ฝั่ง sizing ถ้าไม่ระบุ ลูกค้าจะถามว่าทำไมใช้ไป 400 GB
   แต่ดิสก์ขึ้น 560 GB แล้วเราตอบไม่ได้
2. **ต้องเช็คก่อนสร้าง ไม่ใช่หลังสร้าง** — Studio ไม่รู้ขนาดผลลัพธ์จนกว่าจะ generate เสร็จ ซึ่งเป็นขั้นที่แพงที่สุด
   (GPU time) ถ้าไปเช็คตอนจะเขียน DB = เผา GPU ทิ้งฟรี รูปแบบที่ถูกคือ **pre-check ด้วยค่าประมาณ
   ต่อ media type → generate → reconcile ด้วยขนาดจริง** และ reject ทันทีถ้าเกินเพดานอยู่ก่อนแล้ว
3. **ต้องมี reconcile job** — generation ที่ fail กลางคัน, การลบด้วยมือ, และ API restart ตอน background task
   ค้าง (`PLAN.md` Task 3.12 — ทราบปัญหาแล้วแต่ยังไม่แก้) ทำให้ตัวนับ drift สะสม ตัวนับที่ reconcile ไม่ได้
   = ตัวนับที่เชื่อไม่ได้ = quota ที่บังคับไม่ได้
4. **ห้าม reuse `services/quota.py`** — ตัวเดิมเป็น token quota ที่รู้ค่าแน่นอนก่อนหัก และ docstring ระบุเอง
   ว่า *"consumed ONLY for external API calls"* ⇒ **ข้ามโมเดล local ทั้งหมด ซึ่งคือ path หลักของ on-prem**
   storage quota ต้องเป็นกลไกแยกต่างหาก

### 7.6 กับดักที่ retention **ไม่ได้** แก้ให้

- **`audit_log` ลบไม่ได้** (`CLAUDE.md`, PLAN §7.3) — retention ใช้ไม่ได้ ต้อง partition แล้ว detach
  ไป cold storage แทน; migration `0003_audit_partitions` เคยมีแต่ถูกลบไป **ต้องเอากลับมา**
- **`DELETE` ใน Postgres ไม่คืนพื้นที่ให้ OS** — autovacuum แค่ mark ว่า reuse ได้ ไฟล์ไม่หด
  ยิ่ง media เป็น base64 ใน TOAST ยิ่ง bloat หนัก จะให้หดจริงต้อง `VACUUM FULL`/`pg_repack`
  ซึ่งต้องการที่ว่าง ~2 เท่าชั่วคราว + lock ⇒ **นี่คือเหตุผลที่ "ย้าย media ออกจาก Postgres" คือทางแก้ที่ถูกต้อง
  ไม่ใช่แค่ retention** (บนดิสก์ ลบแล้วได้คืนทันที) — และเป็นเหตุผลหนึ่งของ reserve 15%
- **HNSW index ไม่คืนพื้นที่จากแถวที่ลบเช่นกัน** — ลบไฟล์เยอะ ๆ ต้อง `REINDEX CONCURRENTLY` ตามด้วย
  ควรใส่ไว้ในแผน maintenance window

### 7.7 GPU และ concurrency เมื่อเผื่อ 15%

| Tier | Users | Concurrent (10% + 15%) | VRAM ที่ต้องมี |
|---|---|---|---|
| Standard | 200 | ~23 | 48 GB (หรือ 2×24 GB + LB) |
| Professional | 500 | ~58 | 2×48 GB |
| Enterprise | 1000 | ~115 | 4×48 GB หรือ 2×80 GB |

งบ VRAM ต่อโมเดลก็ควรเผื่อ 15% เช่นกัน (KV cache พุ่งที่ context ยาว): แผนเดิม ~14.5 GB → ~16.7 GB
(24 GB ยังพอ) แต่ถ้าใช้ตัวเลข `PLAN.md` §8 ที่ ~17.2 GB → ~19.8 GB (24 GB **ตึงมาก**)
และ `gemma4:26b` ที่ deploy จริง → **แนะนำ 32–48 GB** ทุกกรณี

### 7.8 ลำดับงานที่ต้องทำ (เรียงตาม ROI)

| # | งาน | เหตุผล |
|---|---|---|
| 1 | **Scheduler** | ตัวปลดล็อกทุกอย่าง — ยังไม่มีเลย (`workers/__init__.py` ว่าง) เลือก asyncio periodic task ใน lifespan (ถูกสุด เข้ากับ single-process ที่ deploy อยู่) หรือ pg_cron (ต้อง build image เอง — `pgvector/pgvector:pg16` ไม่มีมาให้) |
| 2 | **ย้าย Studio media ออกจาก Postgres** | ประหยัดพื้นที่มากสุด + แก้กับดัก §7.6 ข้อ 2 + ทำให้ `pg_dump`/RTO ≤4 ชม. กลับมาเป็นไปได้ |
| 3 | **Storage quota + accounting** (ต่อ user, ต่อ workspace) | ตาม §7.5 |
| 4 | **ปุ่มลบ conversation + generation** | soft-delete เนื้อหา แต่คง audit row ไว้ |
| 5 | **Retention job** | message content 30 วัน (D14) + media 90 วัน |
| 6 | **`audit_log` partitioning + detach/archive** | §7.6 ข้อ 1 |
| 7 | `halfvec` migration | ทำทีหลังได้ แต่คุ้ม — จำเป็นเฉพาะทางเลือก (B) |

ข้อ 1–5 คือชุดที่ทำให้ §2 เปลี่ยนจาก "cumulative เดาไม่ได้" เป็น "steady-state ที่การันตีได้"
ประเมินคร่าว ๆ เป็นงานระดับ **1 sprint** ไม่ใช่ 1 วัน และ **ทุกข้อต้องเสร็จก่อน** ตัวเลข 500 GB / 1 TB
จะกลายเป็นคำสัญญาที่ทำได้จริง

> **ประโยคเดียวสำหรับทีมขาย:** *ตัวนับไม่ได้ทำให้เครื่องเก็บข้อมูลได้มากขึ้น แต่ทำให้เราขายพื้นที่เท่าเดิม
> ได้ในราคาที่สูงขึ้น และพูดตัวเลขได้โดยไม่ต้องเดา*

---

*หมายเหตุถึงผู้ดูแล deck: `docs/deck/ch-ai-gateway-slide-additions.md` (บรรทัด 255) ระบุว่า deployment tiers
"already exist" ใน `CH-AI_Gateway_Product_Presentation.pdf` หน้า 18 ซึ่งไม่มีอยู่ในโค้ดนี้ — หากชื่อ tier ในไฟล์นั้น
ไม่ตรงกับ On-premise / Hybrid / Cloud GPU ที่ใช้ในเอกสารนี้ ควรปรับหัวข้อให้ตรงกันก่อนนำไปใช้จริง*
