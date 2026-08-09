# Server Spec — 3 Tiers (slide-ready)

*Relabeled จาก draft ภาพ "Server Spec / VRAM Budget" ให้ตรงกับชื่อ tier ที่ใช้ทั้งเอกสารแล้ว:
**Standard / Professional / Enterprise** (`report_merge.md` §9, `docs/deck/server-spec.md` §2)
โมเดลเป้าหมายอัปเดตเป็น **Gemma 4 31B** และตัวเลข VRAM/concurrency คำนวณใหม่ทั้งหมดใน §3*

| | |
|---|---|
| **ไฟล์นี้คือ** | ตารางพร้อมวางสไลด์ขาย — all-in-one node ต่อ tier + การคำนวณที่รองรับตัวเลขนั้น |
| **ที่มาของตัวเลขเชิงระบบ** | [`docs/deck/server-spec.md`](./server-spec.md) — sizing assumptions, storage, gap analysis |
| **แถวฟีเจอร์เชิงพาณิชย์ที่ขยายความ** | [`report_merge.md`](../../report_merge.md) §9 |
| **วันที่** | 7 ส.ค. 2026 |

> ⚠️ **ตัวเลข concurrency ในไฟล์นี้ต่ำกว่าที่ draft สไลด์เดิมเสนอไว้มาก** — draft เดิม (23/58/116) สมมติว่า
> ตัวจำกัดคือ VRAM แต่การคำนวณใน §3 แสดงว่าตัวจำกัดจริงคือ **compute ตอน prefill** ⇒ อ่าน §3.4 ก่อนใช้ตัวเลขใดๆ กับลูกค้า

---

## 1. ตารางที่ 1 — Server Spec

*(all-in-one node: App + DB + Inference อยู่เครื่องเดียว)*

| | Standard | Professional | Enterprise |
|---|---|---|---|
| Users (named seats) | 200 | 500 | 1000 |
| **Peak concurrent chats** | **~9** | **~12** | **~24** |
| GPU | 1× NVIDIA L40S 48 GB | 1× RTX PRO 6000 Blackwell 96 GB (Server Edition) | 2× RTX PRO 6000 Blackwell 96 GB (96 GB ต่อใบ ไม่ pool รวม) |
| LLM หลัก | Gemma 4 31B (4-bit) | Gemma 4 31B (8-bit) | Gemma 4 31B (8-bit) × 2 replica |
| CPU | 16 Cores / 32 Threads (EPYC 9124) | 32 Cores / 64 Threads (EPYC 9354) | 64 Cores / 128 Threads (EPYC 9554) |
| System RAM | 64 GB ECC DDR5 | 128 GB ECC DDR5 | 256 GB ECC DDR5 |
| Storage (RAID 1, ดิบ) | 2 TB NVMe SSD Enterprise | 4 TB NVMe SSD Enterprise | 8 TB NVMe SSD Enterprise |
| Network Speed | 10 GbE | 25 GbE | 25 GbE |

**หมายเหตุ:**

1. **แถว Peak concurrent chats คำนวณจาก prefill compute ไม่ใช่ VRAM** — VRAM รองรับได้มากกว่านี้
   **5.5 เท่า (Standard: 50 seats) ถึง 9 เท่า (Professional/Enterprise: 110 seats ต่อใบ)** ดู §2 และ §3.2
   แต่ compute ตอนอ่าน prompt เป็นตัวจำกัดจริง ตัวเลขข้างบนคือกรณี **dense** ที่ runtime efficiency 40%
   ถ้าโมเดลเป็น MoE จะได้ 66 / 92 / 183 แทน — ต่างกัน 7 เท่า ดู blocker #1
2. **สังเกตว่า Standard → Professional เพิ่ม concurrency ได้น้อยมาก (~9 → ~12)** ทั้งที่ VRAM เพิ่มเท่าตัว
   เพราะ prefill ขึ้นกับ **compute (TFLOPS) ของการ์ด ไม่ใช่ความจุ** และ RTX PRO 6000 แรงกว่า L40S ฝั่ง FP16
   dense แค่ ~1.4 เท่า ส่วน Enterprise ได้ 2 เท่าเพราะมี 2 ใบจริง
   ⇒ **ถ้าต้องการให้ ladder เชิงพาณิชย์ scale ตามราคา ต้องขายเป็นจำนวนการ์ด ไม่ใช่ขนาด VRAM ต่อใบ**
3. **ตัวเลขนี้คือ all-in-one node** ต่างจาก `server-spec.md` §2 ที่แยก App+DB ออกจาก inference node
   — สอดคล้องกันเพราะ CPU/RAM ที่นี่ ≈ App+DB (§2) + GPU host รวมกัน (8c/32 GB + 8c/32 GB = 16c/64 GB ฯลฯ)
   ถ้าลูกค้าเลือกแยกเครื่อง ให้ใช้ตัวแบ่งตาม §2
4. **Storage 2/4/8 TB คือดิสก์ดิบ (RAID 1)** เพดานข้อมูลที่ใช้ได้จริงหลังเผื่อ operational reserve 15%
   อยู่ที่ `server-spec.md` §7.3 (500 GB / 1 TB / 2 TB) — ตารางนี้กว้างพอ ไม่ขัดกัน
5. **"2× 96 GB" ไม่ใช่พูล 192 GB** — RTX PRO 6000 Blackwell ไม่มี NVLink แต่ละใบถือ replica ของตัวเอง

---

## 2. ตารางที่ 2 — VRAM Budget

*Gemma 4 31B · KV cache quantized Q8 · **จองตามจำนวน concurrent chat ที่รองรับได้จริง** (~9 / ~12 / ~24
จาก §3.4) × context 8,192 tokens ต่อผู้ใช้ (ที่มาของเลข 8K ดู §3.1)*

| | Standard · 48 GB | Professional · 96 GB | Enterprise · 96 GB ต่อใบ ×2 |
|---|---|---|---|
| Base LLM (weights) | 16.2 GB (4-bit, Q4_K_M) | 30.7 GB (8-bit, Q8_0) | 30.7 GB ต่อใบ |
| KV Cache @ 8K ctx/คน | 5.0 GB (9 seats) | 6.7 GB (12 seats) | 6.7 GB ต่อใบ (12 seats/ใบ = 24 รวม) |
| Embedding (BGE-M3) | 4 GB | 4 GB | 4 GB |
| **รวม / ความจุ** | **~25 / 48 GB** | **~41 / 96 GB** | **~41 / 96 GB ต่อใบ** |
| ว่างเหลือ | **22.8 GB (47%)** | **54.6 GB (57%)** | **54.6 GB ต่อใบ (57%)** |

**หมายเหตุ:**

- **การ์ดถูกใช้ไปเพียงครึ่งเดียว และนั่นคือข้อเท็จจริงที่ต้องพูดกับลูกค้า** — เมื่อจอง KV ตามจำนวนที่ compute
  รองรับจริง VRAM เหลือ 47–57% ทุก tier ⇒ **VRAM ไม่ใช่สิ่งที่ลูกค้ากำลังซื้อ** สิ่งที่ซื้อคือ compute
  (ดู §1 หมายเหตุข้อ 2 และ §3.4)
- **ที่ว่างนี้ควรแลกเป็น "context ยาวขึ้น" ไม่ใช่ "จำนวนคนมากขึ้น"** — เพิ่มจำนวน seat ไม่ได้เพราะติด compute
  แต่เพิ่มความยาว context ได้ฟรีเพราะติดแค่ VRAM:

  | Tier | KV/คน ที่จ่ายไหว | context สูงสุดต่อคน | ถ้าตั้ง 32K ทุกคน |
  |---|---|---|---|
  | Standard | 3.08 GB | **~66K tokens** | 34.5 / 48 GB ✅ |
  | Professional | 5.11 GB | **~113K tokens** | 53.8 / 96 GB ✅ |
  | Enterprise (ต่อใบ) | 5.11 GB | **~113K tokens** | 53.8 / 96 GB ✅ |

  ⇒ **ตั้ง context 32K ได้ทุก tier โดยยังเหลือที่ว่าง** ซึ่งทำให้ RAG ดึง chunk ได้มากขึ้นและอ่านเอกสารยาวได้
  — เป็นการอัปเกรดคุณภาพที่ไม่มีต้นทุนฮาร์ดแวร์เพิ่ม (แต่ต้องปิด blocker #3 ก่อน เพราะวันนี้ยังไม่ได้ตั้ง `num_ctx` เลย)
- **ถ้าปิด blocker #1/#4 สำเร็จแล้ว concurrency เพิ่มขึ้น** ให้กลับมาคำนวณแถว KV ใหม่ที่ 0.559 GB × seats
  — เพดานที่ VRAM รับได้ @8K คือ **50 seats (Standard)** และ **110 seats ต่อใบ (Professional/Enterprise)**
  ⇒ ถ้ายืนยันว่าเป็น MoE (concurrency 66 / 92 / 183): **Professional และ Enterprise ยังพอดี** (86 / 96 GB)
  แต่ **Standard จะ VRAM ไม่พอ** (ต้องใช้ 57 GB จากการ์ด 48 GB) ⇒ ต้องลด context ต่อคนหรือจำกัด Standard ไว้ที่ 50 concurrent
  — คือจุดที่ Standard จะสลับจาก "ติด compute" มาเป็น "ติด VRAM"
- **แถวที่ตัดออกจาก draft ภาพเดิม — CH-STT / Computer Vision / Image Gen (SDXL) local** ทั้งสามเป็น
  **ผลิตภัณฑ์/Connector แยก** ตาม `ch-ai-gateway-slide-additions.md:211-212` และ `PLAN.md:1329`
  (❌ Voice input/output) ไม่ใช่ Core ที่ `report_merge.md` ครอบคลุม ถ้าขายรวม ให้บวกงบเข้ากับที่ว่าง:
  CH-STT (Whisper large-v3) ~3 GB · Computer Vision (YOLO11 + BoT-SORT) ~2 GB · SDXL ~10 GB
- **AI Studio ใน `report_merge.md` §3 เป็น cloud ไม่ใช่ local** — ภาพ/วิดีโอ/เพลงเรียกผ่าน Gemini / Veo /
  Lyria จึงไม่มีบรรทัดในงบนี้โดยตั้งใจ ไม่ใช่ตกหล่น
- **"Reranker" ใน draft ภาพเดิมถูกถอดชื่อออก** — ระบบมีแต่ BGE-M3 embeddings ตัวเลข 4 GB คงไว้เป็นหัวเผื่อ
  (BGE-M3 Q8 เองใช้จริง ~1.2 GB ตาม `server-spec.md` §3)

---

## 3. การคำนวณ — สเปกนี้ใช้ได้จริงไหม

**สมมติฐานสถาปัตยกรรม** (⚠️ ต้องยืนยันกับสเปกจริงของ Gemma 4 31B ก่อนพิมพ์ — ดู blocker #1):
ใช้ตระกูล Gemma 3 27B ปรับสเกลเป็น 31B — **66 layers · 16 KV heads · head_dim 128 · interleave
local:global 5:1 · sliding window 1,024 tokens**

### 3.1 ทำไม context = 8K ต่อคน

ได้จากโค้ด ไม่ใช่เลือกเอง — `backend/app/config.py:46-47`:

| ส่วนประกอบของ prompt | tokens | ที่มา |
|---|---|---|
| Chunk ที่ดึงมาจาก RAG | **2,500** | `rag_top_k = 5` × `rag_chunk_tokens = 500` |
| System prompt + agent persona + SKILL.md ที่ pin | ~1,000 | `chat_policy.py:151,183` |
| ประวัติสนทนา 8–10 turn | ~2,000 | — |
| คำถาม + หัวเผื่อคำตอบ | ~500 | — |
| **รวม prompt ต่อ turn** | **~4,000** | |
| **จอง KV ต่อคน** | **8,192** | เผื่อบทสนทนายาวขึ้นระหว่าง session |

> เทียบกับ draft ภาพเดิมที่ให้ Standard เพียง 267 MB/คน ≈ **1,500 tokens** — **น้อยกว่า 2,500 tokens
> ที่แค่ chunk RAG อย่างเดียวต้องใช้** ⇒ ตัวเลข KV 6/20/60 GB ในภาพเดิมใช้ไม่ได้ ต้องคำนวณใหม่

### 3.2 VRAM — **ผ่านทุก tier** ✅

```
KV ต่อ token = 2 × layers × kv_heads × head_dim × bytes_per_element
  global layers (11) : เต็ม context          →  0.043 MB/token @Q8
  local layers  (55) : ตันที่ sliding window →  0.351 GB คงที่ต่อ sequence
  ⇒ 8K context @Q8   =  0.559 GB ต่อผู้ใช้
```

| Tier | Weights | + KV (seats ที่รองรับจริง) | + Embed | = รวม | ความจุ | ผล |
|---|---|---|---|---|---|---|
| Standard | 16.2 | 5.0 (9 seats) | 4 | **25.2** | 48 | ✅ เหลือ 22.8 (47%) |
| Professional | 30.7 | 6.7 (12 seats) | 4 | **41.4** | 96 | ✅ เหลือ 54.6 (57%) |
| Enterprise (ต่อใบ) | 30.7 | 6.7 (12 seats/ใบ) | 4 | **41.4** | 96 | ✅ เหลือ 54.6 (57%) |

การขยับ 26B → 31B กินเพิ่มแค่ **+2.6 GB (4-bit) / +4.9 GB (8-bit)** ⇒ **ไม่ต้องเปลี่ยนการ์ดใดๆ**

**VRAM ไม่ใช่คอขวด — และห่างจากการเป็นคอขวดมาก** เมื่อจองตามจำนวนที่ compute รองรับจริง (§3.4)
การ์ดถูกใช้เพียง 43–53% ⇒ ที่ว่างควรแลกเป็น context ยาวขึ้น (ตั้ง 32K ได้ทุก tier) ไม่ใช่ seat เพิ่ม — ดูตารางใน §2

### 3.3 Decode throughput — **ผ่านทุก tier** ✅

decode ติด memory bandwidth: ทุก step ต้องอ่าน weights **บวก KV ของทุก sequence ที่ active**

```
tok/s รวม = bandwidth ÷ (weights + KV ของทุก seat) × จำนวน seat
```

| Tier | อ่าน/step | steps/s | รวม | **ต่อคน** |
|---|---|---|---|---|
| Standard (L40S, 864 GB/s) | 29.1 GB | 29.7 | 683 tok/s | **29.7 tok/s** ✅ |
| Professional (RTX PRO, 1,790 GB/s) | 63.1 GB | 28.4 | 1,646 tok/s | **28.4 tok/s** ✅ |
| Enterprise (ต่อใบ) | 63.1 GB | 28.4 | 1,646 tok/s | **28.4 tok/s** ✅ |

เกณฑ์ที่ผู้ใช้อ่านทัน ~20–25 tok/s ⇒ ผ่านทั้งสามระดับ (และเสมอกันพอดี เพราะการ์ดใหญ่ขึ้นแต่แบก seat มากขึ้นตามกัน)

### 3.4 Prefill — **ตัวบล็อกจริง** ❌

```
FLOPs prefill = 2 × parameters × prompt_tokens
dense 31B, prompt 4K = 2 × 31e9 × 4096 = 254 TFLOP ต่อ 1 คำถาม
```

สมมติแต่ละ turn ถือ slot ไว้ ~30 วินาที ⇒ อัตราคำถามเข้า = seats ÷ 30 ต่อวินาที

| Tier | ถ้าอ้าง concurrency | ต้องการ (ต่อเนื่อง) | การ์ดทำได้จริง (25–55% eff) | **รองรับได้จริง** |
|---|---|---|---|---|
| Standard (L40S, 181 TFLOPS FP16 dense) | 23 | 195 TFLOPS | 45–100 TFLOPS | **5–12 chat** |
| Professional (RTX PRO ~250 TFLOPS) | 58 | 491 TFLOPS | 62–138 TFLOPS | **7–16 chat** |
| Enterprise (×2 ใบ) | 116 | 491 TFLOPS/ใบ | 62–138 TFLOPS/ใบ | **15–33 chat** |

**ถ้าโมเดลเป็น MoE active-4B** (32.8 TFLOP ต่อ prompt แทน 254): รองรับ **66 / 92 / 183 chat** ⇒ ผ่านสบายทุก tier

> **จุดยืนยันซึ่งกันและกัน:** Standard ที่ ~9 chat (dense, eff 40%) **ตรงกับเพดาน DB connection pool
> ~7–8 chat ที่ `server-spec.md` §6.1 คำนวณไว้อย่างอิสระจากคนละทาง** ⇒ สองเพดานนี้อยู่ระดับเดียวกันพอดี
> ซึ่งแปลว่าการแก้ทีละอย่างจะไม่ช่วยอะไร ต้องแก้คู่กัน

### 3.5 ปิดคำถามค้างของ `server-spec.md` §3

§3 ตั้งคำถามไว้ว่า README (~2.7 GB) กับ `PLAN.md` §8 (~6 GB) ตัวไหนถูก — **ถูกทั้งคู่**
Qwen2.5-14B (48 layers, 8 KV heads, head_dim 128) @ 32K context: **6.00 GB ที่ fp16 · 3.00 GB ที่ Q8**
เป็นคนละ KV precision ไม่ใช่ตัวเลขที่ขัดกัน

---

## 4. Blockers — ต้องปิดก่อนตัวเลขในเอกสารนี้เป็นคำสัญญาได้

| # | Blocker | ผล | หลักฐาน |
|---|---|---|---|
| **1** | **dense หรือ MoE?** ชื่อ `Gemma 4 31B` ไม่ระบุ และไม่มีคำว่า MoE/A4B ที่ไหนในโค้ดเลย | ตัวแปรเดียวที่ตัดสินว่า concurrency คือ **9/12/24 (dense) หรือ 66/92/183 (MoE)** — ต่างกัน 7 เท่า เอกสารนี้ตั้ง default เป็น dense (อนุรักษ์นิยม) | — |
| **2** | **deployment ยังเป็น 26B** | ถ้าสเปกขายเป็น 31B ต้องเปลี่ยน deployment ด้วย ไม่งั้นเอกสารกับเครื่องจริงไม่ตรงกัน | `.env:33`, `docker-compose.yml:34` = `gemma4:26b` |
| **3** | **ไม่เคยตั้ง `num_ctx` เลย** | context จริงคือ default ของ Ollama (2K–4K) **ไม่ใช่ 8K ที่ §2 จองไว้** และ prompt RAG ที่ยาวกว่านั้น **ถูกตัดทิ้งเงียบๆ** ⇒ ตาราง §2 เป็นเพียงทฤษฎีจนกว่าจะตั้งค่านี้ | `backend/app/llm/llamacpp.py:41-47, 144-157` — payload ไม่มี `options` |
| **4** | **ลำดับ prompt ทำให้ prefix cache แตกทุก turn** | เรียง system → **RAG** → history → user ⇒ RAG (ก้อนที่เปลี่ยนทุก turn) อยู่ก่อน history ที่คงที่ ⇒ cache แตกตั้งแต่ต้น ทุก turn ต้อง prefill ประวัติใหม่หมด **ย้าย RAG ไปไว้หลัง history** จะ cap prefill ต่อ turn ไว้ที่ ~2,700 tokens คงที่ แทนที่จะโตตามความยาวบทสนทนา — **ทางแก้ prefill ที่ถูกที่สุด ไม่ต้องซื้อการ์ด** | `backend/app/agents/orchestrator.py:135-144` |
| **5** | **runtime เป็น Ollama ไม่ใช่ vLLM** | ไม่มี chunked prefill / continuous batching ระดับ production ⇒ efficiency อยู่ปลายล่างของช่วง 25–55% | `backend/app/llm/llamacpp.py` |
| **6** | **ยังไม่เคยวัดจริงบน GPU** | ตัวเลข effective TFLOPS (25–55%) เป็นช่วงอ้างอิงทั่วไปของอุตสาหกรรม **ไม่ใช่ผลวัดของเครื่องนี้** | `production_improvement.md` gap #15 |

### ข้อจำกัดเชิงระบบที่ต้องแจ้งพร้อมตารางเสมอ

| ข้อจำกัด | ผล | ที่มา |
|---|---|---|
| DB connection pool ไม่ได้ตั้งค่า (default 5+10 = 15 conn) | ~7–8 chat พร้อมกัน **ทุก tier เท่ากัน** — เพดานนี้ต่ำกว่าทุกตัวเลขใน §3.4 | `server-spec.md` §6.1, `backend/app/db.py:7` |
| Task 3.7 (multi-instance + load balancer) ยังไม่ได้ทำ | แถว Enterprise "× 2 replica" **ยังส่งมอบไม่ได้จริงวันนี้** | `PLAN.md` Task 3.7 |
| `LLM_KEEP_ALIVE=0` | โมเดล unload ทุก request ⇒ §2 สมมติว่าโมเดลค้างพร้อมกัน ต้องแก้ config ก่อน | `backend/app/config.py:35-38` |
| `--reload` override `--workers 4` | คอลัมน์ CPU ใน §1 ยังไม่ถูกใช้ประโยชน์จริงฝั่ง API | `docker-compose.yml:22` |

> **ประโยคเดียวสำหรับทีมขาย:** VRAM ในสเปกนี้ **พอ** และ decode **เร็วพอ** — สิ่งที่ยังไม่พอคือ compute
> ตอนอ่าน prompt ซึ่งแก้ได้ด้วยงานซอฟต์แวร์ (blocker #3/#4/#5) มากกว่าด้วยการซื้อการ์ดเพิ่ม
> ⇒ อย่าขายตัวเลข concurrency ก่อนปิด blocker #1 และวัดจริงบนเครื่อง
