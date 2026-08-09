'use client'

import { useEffect, useState } from 'react'
import { Ic } from './Icon'

export default function ThemeToggle() {
  const [dark, setDark] = useState(false)

  useEffect(() => {
    setDark(localStorage.getItem('dca_dark') === 'true')
  }, [])

  function toggle() {
    const next = !dark
    setDark(next)
    if (next) {
      document.documentElement.setAttribute('data-theme', 'dark')
    } else {
      document.documentElement.removeAttribute('data-theme')
    }
    localStorage.setItem('dca_dark', String(next))
  }

  return (
    <button
      onClick={toggle}
      aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      style={{
        position: 'fixed',
        bottom: 16,
        right: 16,
        width: 32,
        height: 32,
        borderRadius: 'var(--radius-full)',
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--muted)',
        boxShadow: 'var(--shadow)',
        zIndex: 9999,
        padding: 0,
        transition: 'color 0.15s, background 0.15s, border-color 0.15s',
      }}
    >
      {dark ? <Ic.Sun size={15} /> : <Ic.Moon size={15} />}
    </button>
  )
}
