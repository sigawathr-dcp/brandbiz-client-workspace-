'use client'

import { useEffect, useRef, useState } from 'react'
import { Ic } from './ui/Icon'
import ProviderMark from './ui/ProviderMark'
import { MODEL_BY_CODE } from '@/lib/domain'

interface ModelOption {
  code: string
  display_name: string
  provider: string
  is_local: boolean
}

interface ModelPickerProps {
  value: string
  onChange: (code: string) => void
}

export default function ModelPicker({ value, onChange }: ModelPickerProps) {
  const [models, setModels] = useState<ModelOption[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch('/api/models')
      .then(r => r.ok ? r.json() : [])
      .then((data: ModelOption[]) => {
        setModels(data)
        if (value !== 'auto' && !data.find(m => m.code === value)) onChange('auto')
      })
      .catch(() => setModels([]))
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [])

  const options: ModelOption[] = [
    { code: 'auto', display_name: 'Auto (local)', provider: 'local', is_local: true },
    ...models.filter(m => !m.is_local),
  ]

  const sel = options.find(m => m.code === value) ?? options[0]
  const selInfo = MODEL_BY_CODE[value] ?? {
    label: sel?.display_name ?? value,
    provider: sel?.provider ?? 'local',
    isLocal: true,
  }

  return (
    <div ref={ref} style={{ position: 'relative', flexShrink: 0 }}>
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => !loading && setOpen(o => !o)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 9,
          padding: '7px 10px 7px 8px',
          background: 'var(--surface)',
          border: '1px solid var(--line-2)',
          borderRadius: 'var(--r-md)',
          color: 'var(--ink)',
          boxShadow: 'var(--shadow-1)',
          cursor: loading ? 'default' : 'pointer',
        }}
      >
        <ProviderMark provider={selInfo.provider} isLocal={selInfo.isLocal} size={24} />
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', lineHeight: 1.15 }}>
          <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)' }}>{selInfo.label}</span>
          <span style={{ fontSize: 10.5, color: 'var(--ink-3)' }}>{selInfo.provider}</span>
        </span>
        <Ic.chevron
          size={16}
          style={{
            color: 'var(--ink-3)',
            marginLeft: 2,
            transform: open ? 'rotate(180deg)' : 'none',
            transition: '.2s',
          }}
        />
      </button>

      {/* Dropdown — opens upward */}
      {open && (
        <div style={{
          position: 'absolute',
          bottom: 'calc(100% + 8px)',
          right: 0,
          width: 340,
          maxHeight: 'min(480px, calc(100vh - 120px))',
          overflowY: 'auto',
          background: 'var(--surface)',
          border: '1px solid var(--line)',
          borderRadius: 'var(--r-lg)',
          boxShadow: 'var(--shadow-3)',
          padding: 7,
          zIndex: 60,
          animation: 'popIn .14s ease',
        }}>
          <div style={{
            padding: '6px 9px 8px',
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '.04em',
            textTransform: 'uppercase',
            color: 'var(--ink-4)',
          }}>
            Choose a model
          </div>
          {options.map(m => {
            const info = MODEL_BY_CODE[m.code] ?? {
              label: m.display_name,
              provider: m.provider,
              isLocal: m.is_local,
              blurb: m.is_local ? 'Local inference' : 'External API',
            }
            const isSel = m.code === value
            return (
              <button
                key={m.code}
                type="button"
                onClick={() => { onChange(m.code); setOpen(false) }}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                  textAlign: 'left',
                  padding: '9px 10px',
                  borderRadius: 'var(--r-md)',
                  border: 'none',
                  background: isSel ? 'var(--accent-weak)' : 'transparent',
                  cursor: 'pointer',
                }}
                onMouseEnter={e => { if (!isSel) e.currentTarget.style.background = 'var(--surface-2)' }}
                onMouseLeave={e => { if (!isSel) e.currentTarget.style.background = 'transparent' }}
              >
                <ProviderMark provider={info.provider} isLocal={info.isLocal} size={30} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                    <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)' }}>{info.label}</span>
                    {info.free && (
                      <span style={{
                        fontSize: 10,
                        fontWeight: 600,
                        color: 'var(--t1)',
                        background: 'var(--t1-bg)',
                        padding: '1px 6px',
                        borderRadius: 99,
                      }}>
                        FREE
                      </span>
                    )}
                    {isSel && (
                      <Ic.check size={15} strokeWidth={2.4} style={{ color: 'var(--accent)', marginLeft: 'auto' }} />
                    )}
                  </span>
                  <span style={{
                    display: 'block',
                    fontSize: 11.5,
                    color: 'var(--ink-3)',
                    marginTop: 2,
                    lineHeight: 1.35,
                  }}>
                    {info.blurb ?? (info.isLocal ? 'Local inference' : 'External API')}
                  </span>
                </span>
              </button>
            )
          })}
          <div style={{
            borderTop: '1px solid var(--line)',
            margin: '6px 4px 0',
            padding: '8px 6px 4px',
            fontSize: 11,
            color: 'var(--ink-4)',
            display: 'flex',
            gap: 6,
            alignItems: 'flex-start',
          }}>
            <Ic.info size={13} style={{ flex: 'none', marginTop: 1 }} />
            <span>Sensitive messages always run on the local model, whatever you pick here.</span>
          </div>
        </div>
      )}
    </div>
  )
}
