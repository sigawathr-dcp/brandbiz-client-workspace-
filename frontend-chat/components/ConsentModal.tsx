'use client'

import { useState } from 'react'
import { Ic } from './ui/Icon'

interface ConsentModalProps {
  onAcknowledged: () => void
}

export default function ConsentModal({ onAcknowledged }: ConsentModalProps) {
  const [lang, setLang]       = useState<'th' | 'en'>('th')
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  async function handleAcknowledge() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/consent', { method: 'POST' })
      if (!res.ok) throw new Error('failed')
      onAcknowledged()
    } catch {
      setError(lang === 'th' ? 'เกิดข้อผิดพลาด กรุณาลองใหม่' : 'An error occurred. Please try again.')
      setLoading(false)
    }
  }

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 9999,
      background: 'rgba(0,0,0,0.55)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '1rem',
      backdropFilter: 'blur(4px)',
      animation: 'fadeIn 0.15s ease',
    }}>
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-xl)',
        padding: '28px 28px 24px',
        maxWidth: 540,
        width: '100%',
        boxShadow: 'var(--shadow-xl)',
        animation: 'popIn 0.2s ease',
      }}>

        {/* Header row */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36, height: 36,
              borderRadius: 'var(--radius)',
              background: 'var(--accent-subtle)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              <Ic.Shield size={18} style={{ color: 'var(--accent)' }} />
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>
                {lang === 'th' ? 'แจ้งความยินยอมเรื่องความเป็นส่วนตัว' : 'Privacy Notice & Consent'}
              </h2>
              <p style={{ margin: 0, fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
                {lang === 'th' ? 'กรุณาอ่านก่อนใช้งาน' : 'Please read before continuing'}
              </p>
            </div>
          </div>

          {/* Language toggle */}
          <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
            {(['th', 'en'] as const).map(l => (
              <button
                key={l}
                onClick={() => setLang(l)}
                style={{
                  padding: '3px 10px',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 11,
                  fontWeight: 600,
                  background: lang === l ? 'var(--accent)' : 'transparent',
                  color: lang === l ? '#fff' : 'var(--muted)',
                  border: `1px solid ${lang === l ? 'var(--accent)' : 'var(--border)'}`,
                  cursor: 'pointer',
                  transition: 'background 0.15s, color 0.15s',
                }}
              >
                {l === 'th' ? 'ไทย' : 'EN'}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div style={{
          fontSize: 13,
          lineHeight: 1.75,
          color: 'var(--text-2)',
        }}>
          {lang === 'th' ? <ThaiContent /> : <EnglishContent />}
        </div>

        {/* Error */}
        {error && (
          <p style={{
            marginTop: 12,
            fontSize: 12,
            color: 'var(--danger)',
            background: 'var(--danger-bg)',
            border: '1px solid var(--t4-border)',
            borderRadius: 'var(--radius-sm)',
            padding: '6px 10px',
          }}>
            {error}
          </p>
        )}

        {/* CTA */}
        <div style={{ marginTop: 20 }}>
          <button
            onClick={handleAcknowledge}
            disabled={loading}
            style={{
              width: '100%',
              padding: '11px',
              background: loading ? 'var(--border)' : 'var(--accent)',
              color: loading ? 'var(--muted)' : '#fff',
              border: 'none',
              borderRadius: 'var(--radius)',
              fontSize: 14,
              fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'background 0.2s',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
            }}
          >
            {loading
              ? (lang === 'th' ? 'กำลังบันทึก…' : 'Saving…')
              : (
                <>
                  <Ic.CheckCircle size={15} />
                  {lang === 'th' ? 'ฉันเข้าใจและยอมรับ' : 'I Understand and Accept'}
                </>
              )
            }
          </button>
        </div>

        <p style={{ marginTop: 10, fontSize: 11, color: 'var(--muted)', textAlign: 'center' }}>
          {lang === 'th'
            ? <>อ่านนโยบายฉบับเต็มได้ที่ <a href="/privacy-policy" target="_blank" style={{ color: 'var(--accent)' }}>นโยบายความเป็นส่วนตัว</a></>
            : <>Full policy at <a href="/privacy-policy" target="_blank" style={{ color: 'var(--accent)' }}>Privacy Policy</a></>
          }
        </p>
      </div>
    </div>
  )
}

function ConsentPoint({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={{
      display: 'flex',
      gap: 10,
      padding: '8px 0',
      borderBottom: '1px solid var(--border)',
    }}>
      <span style={{ color: 'var(--accent)', flexShrink: 0, marginTop: 1 }}>{icon}</span>
      <span>{children}</span>
    </div>
  )
}

function ThaiContent() {
  return (
    <div>
      <p style={{ marginBottom: 12, color: 'var(--text)' }}>
        ระบบ AI Gateway นี้เป็น <strong>บริการภายในองค์กร</strong> เท่านั้น
        ไม่ใช่บริการสาธารณะของ Anthropic หรือผู้ให้บริการรายอื่น
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', marginBottom: 14 }}>
        <ConsentPoint icon={<Ic.Database size={14} />}>
          ระบบบันทึก <strong>ข้อความ คำตอบ Model ที่ใช้ Token วันเวลา IP และระดับข้อมูล</strong>
        </ConsentPoint>
        <ConsentPoint icon={<Ic.Clock size={14} />}>
          เนื้อหาข้อความจะ<strong>ลบอัตโนมัติหลัง 30 วัน</strong> — Metadata เก็บตามกฎหมาย
        </ConsentPoint>
        <ConsentPoint icon={<Ic.Lock size={14} />}>
          ข้อมูลเข้ารหัส <strong>AES-256-GCM</strong> การเปิดดูต้องผ่าน <strong>4-eyes approval</strong> และคุณจะได้รับแจ้งเสมอ
        </ConsentPoint>
        <ConsentPoint icon={<Ic.Shield size={14} />}>
          ข้อมูล Tier 3/4 จะ<strong>ไม่ถูกส่งออกไปยัง API ภายนอก</strong> — ใช้ Local Model โดยอัตโนมัติ
        </ConsentPoint>
      </div>
      <div style={{
        padding: '8px 12px',
        background: 'var(--accent-subtle)',
        borderLeft: '3px solid var(--accent)',
        borderRadius: 'var(--radius-sm)',
        fontSize: 12,
        color: 'var(--text-2)',
      }}>
        ระบบนี้ออกแบบให้สอดคล้องกับ <strong>พ.ร.บ. คุ้มครองข้อมูลส่วนบุคคล (PDPA) พ.ศ. 2562</strong>{' '}
        หากมีคำถาม ติดต่อทีม IT Security
      </div>
    </div>
  )
}

function EnglishContent() {
  return (
    <div>
      <p style={{ marginBottom: 12, color: 'var(--text)' }}>
        This AI Gateway is an <strong>internal company tool</strong> only.
        It is not Anthropic&apos;s consumer service or any other public AI product.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', marginBottom: 14 }}>
        <ConsentPoint icon={<Ic.Database size={14} />}>
          We log your <strong>prompts, responses, model used, token counts, timestamps, IP, and data tier</strong>.
        </ConsentPoint>
        <ConsentPoint icon={<Ic.Clock size={14} />}>
          Message content is <strong>auto-deleted after 30 days</strong>. Metadata is retained per legal requirements.
        </ConsentPoint>
        <ConsentPoint icon={<Ic.Lock size={14} />}>
          All content is encrypted with <strong>AES-256-GCM</strong>. Decryption requires <strong>4-eyes admin approval</strong> — you will always be notified.
        </ConsentPoint>
        <ConsentPoint icon={<Ic.Shield size={14} />}>
          Tier 3/4 data (PII, M&amp;A) is <strong>never sent to external APIs</strong> — the system automatically uses the local model.
        </ConsentPoint>
      </div>
      <div style={{
        padding: '8px 12px',
        background: 'var(--accent-subtle)',
        borderLeft: '3px solid var(--accent)',
        borderRadius: 'var(--radius-sm)',
        fontSize: 12,
        color: 'var(--text-2)',
      }}>
        This system complies with Thailand&apos;s <strong>Personal Data Protection Act (PDPA) B.E. 2562</strong>.
        Questions? Contact IT Security.
      </div>
    </div>
  )
}
