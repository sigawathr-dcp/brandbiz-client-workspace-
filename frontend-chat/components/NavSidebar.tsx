'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { Ic } from './ui/Icon'
import QuotaMeter from './QuotaMeter'
import { canUseTasks } from '@/lib/domain'

interface UserInfo {
  id: string
  email: string
  display_name: string | null
  avatar_url: string | null
  role: string
  workspace_id?: string | null // D23 — set for a client-workspace seat using this app
}

interface NavSidebarProps {
  user: UserInfo | null
  /** Pass conversation list JSX here for the chat view; omit for admin view */
  children?: React.ReactNode
}

function NavItem({
  href,
  icon,
  label,
  active,
  badge,
}: {
  href: string
  icon: React.ReactNode
  label: string
  active?: boolean
  badge?: string
}) {
  return (
    <Link href={href} style={{ display: 'block', textDecoration: 'none' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 11,
          padding: '8px 10px',
          borderRadius: 'var(--r-md)',
          marginBottom: 1,
          background: active ? 'var(--accent-weak)' : 'transparent',
          color: active ? 'var(--ink)' : 'var(--ink-2)',
          fontWeight: active ? 600 : 500,
          fontSize: 13.5,
          textDecoration: 'none',
          transition: 'background 0.1s',
          cursor: 'pointer',
        }}
        onMouseEnter={e => {
          if (!active) (e.currentTarget as HTMLDivElement).style.background = 'var(--surface-2)'
        }}
        onMouseLeave={e => {
          if (!active) (e.currentTarget as HTMLDivElement).style.background = 'transparent'
        }}
      >
        <span style={{ color: active ? 'var(--accent)' : 'var(--ink-3)', flex: 'none' }}>{icon}</span>
        <span style={{ flex: 1 }}>{label}</span>
        {badge && (
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            color: 'var(--ink-4)',
            background: 'var(--surface-2)',
            padding: '1px 7px',
            borderRadius: 99,
          }}>
            {badge}
          </span>
        )}
      </div>
    </Link>
  )
}

function SectionLabel({ label }: { label: string }) {
  return (
    <div style={{
      fontSize: 11,
      fontWeight: 600,
      color: 'var(--ink-4)',
      textTransform: 'uppercase',
      letterSpacing: '.04em',
      padding: '8px 4px 6px 10px',
    }}>
      {label}
    </div>
  )
}

export default function NavSidebar({ user, children }: NavSidebarProps) {
  const path = usePathname()
  const router = useRouter()
  const isAdmin = user?.role === 'ADMIN'
  const isChatMode = children !== undefined
  const showTasks = !!user && canUseTasks(user.role)

  const initials = user?.display_name
    ? user.display_name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase()
    : (user?.email?.[0] ?? '?').toUpperCase()

  const roleLabel = user?.role === 'ADMIN'
    ? 'Administrator'
    : user?.role ?? ''

  async function handleLogout() {
    await fetch('/api/logout', { method: 'POST' }).catch(() => {})
    router.push('/login')
    router.refresh()
  }

  return (
    <aside className="nav-sidebar" style={{
      background: 'var(--surface)',
      borderRight: '1px solid var(--line)',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Logo */}
      <div style={{ padding: '16px 16px 12px', display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 30,
          height: 30,
          borderRadius: 8,
          background: 'var(--accent)',
          color: '#fff',
          display: 'grid',
          placeItems: 'center',
          boxShadow: 'var(--shadow-1)',
          flexShrink: 0,
        }}>
          <Ic.shield size={17} strokeWidth={2.1} />
        </div>
        <div style={{ lineHeight: 1.1 }}>
          <div style={{ fontWeight: 700, fontSize: 14.5, letterSpacing: '-.01em', color: 'var(--ink)' }}>Decomplica AI</div>
          <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>Gateway</div>
        </div>
      </div>

      {/* D23 — client-workspace seat using the internal app: a way back to
          the น้องภูมิ funnel it started from. Internal staff have no
          workspace_id, so this never renders for them. */}
      {user?.workspace_id && (
        <div style={{ padding: '0 10px 8px', flexShrink: 0 }}>
          <NavItem
            href="/w"
            icon={<Ic.globe size={17} strokeWidth={path === '/w' || path.startsWith('/w/') ? 2.1 : 1.8} />}
            label="Brandbiz workspace"
            active={path === '/w' || path.startsWith('/w/')}
          />
        </div>
      )}

      {/* Primary nav */}
      <div style={{ padding: '0 10px 8px', display: 'flex', flexDirection: 'column', gap: 2, flexShrink: 0 }}>
        <NavItem
          href="/chat"
          icon={<Ic.message size={17} strokeWidth={path.startsWith('/chat') && !path.startsWith('/chat/knowledge') && path !== '/chat/search' ? 2.1 : 1.8} />}
          label="Chat"
          active={path.startsWith('/chat') && !path.startsWith('/chat/knowledge') && path !== '/chat/search'}
        />
        <NavItem
          href="/chat/knowledge"
          icon={<Ic.database size={17} strokeWidth={path.startsWith('/chat/knowledge') ? 2.1 : 1.8} />}
          label="Knowledge base"
          active={path.startsWith('/chat/knowledge')}
        />
        <NavItem
          href="/studio"
          icon={<Ic.spark size={17} strokeWidth={path.startsWith('/studio') ? 2.1 : 1.8} />}
          label="AI Studio"
          active={path.startsWith('/studio')}
        />
        <NavItem
          href="/library"
          icon={<Ic.Package size={17} strokeWidth={path.startsWith('/library') ? 2.1 : 1.8} />}
          label="Library"
          active={path.startsWith('/library')}
        />
        <NavItem
          href="/agent"
          icon={<Ic.cpu size={17} strokeWidth={path.startsWith('/agent') ? 2.1 : 1.8} />}
          label="AI Agent"
          active={path.startsWith('/agent')}
        />
        <NavItem
          href="/skills"
          icon={<Ic.layers size={17} strokeWidth={path.startsWith('/skills') ? 2.1 : 1.8} />}
          label="Skills"
          active={path.startsWith('/skills')}
        />
        {showTasks && (
          <NavItem
            href="/tasks"
            icon={<Ic.clock size={17} strokeWidth={path.startsWith('/tasks') ? 2.1 : 1.8} />}
            label="Tasks"
            active={path.startsWith('/tasks')}
          />
        )}
        {isAdmin && (
          <NavItem
            href="/admin-console"
            icon={<Ic.sliders size={17} strokeWidth={path === '/admin-console' ? 2.1 : 1.8} />}
            label="Admin console"
            active={path === '/admin-console'}
          />
        )}
      </div>

      {/* New chat button — chat mode only */}
      {isChatMode && (
        <div style={{ padding: '0 12px 10px', flexShrink: 0 }}>
          <Link href="/chat" style={{ display: 'block', textDecoration: 'none' }}>
            <button
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                padding: '10px',
                borderRadius: 'var(--r-md)',
                border: '1px solid var(--line-2)',
                background: 'var(--surface)',
                color: 'var(--ink)',
                fontWeight: 600,
                fontSize: 13.5,
                boxShadow: 'var(--shadow-1)',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-2)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'var(--surface)')}
            >
              <Ic.plus size={16} strokeWidth={2.2} /> New chat
            </button>
          </Link>
        </div>
      )}

      {/* Search chats — chat mode only */}
      {isChatMode && (
        <div style={{ padding: '0 10px 8px', flexShrink: 0 }}>
          <NavItem
            href="/chat/search"
            icon={<Ic.search size={16} strokeWidth={path === '/chat/search' ? 2.1 : 1.8} />}
            label="Search chats"
            active={path === '/chat/search'}
          />
        </div>
      )}

      {/* Admin governance section */}
      {isAdmin && (
        <div style={{ padding: '0 10px 8px', flexShrink: 0 }}>
          <SectionLabel label="Governance" />
          <NavItem
            href="/audit"
            icon={<Ic.eye size={16} strokeWidth={1.8} />}
            label="Audit log"
            active={path === '/audit'}
            badge="live"
          />
          <NavItem
            href="/reveal"
            icon={<Ic.layers size={16} strokeWidth={1.8} />}
            label="Reveal queue"
            active={path === '/reveal'}
          />
          <NavItem
            href="/users"
            icon={<Ic.users size={16} strokeWidth={1.8} />}
            label="Users"
            active={path === '/users'}
          />
          <NavItem
            href="/vault-sync"
            icon={<Ic.RefreshCw size={16} strokeWidth={1.8} />}
            label="Vault sync"
            active={path === '/vault-sync'}
          />
          <NavItem
            href="/leads"
            icon={<Ic.message size={16} strokeWidth={1.8} />}
            label="Expert leads"
            active={path === '/leads'}
          />
          <NavItem
            href="/clients"
            icon={<Ic.globe size={16} strokeWidth={1.8} />}
            label="Client workspaces"
            active={path === '/clients' || path.startsWith('/clients/')}
          />
        </div>
      )}

      {/* Conversation list slot — chat mode only */}
      {isChatMode && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 8px 8px', minHeight: 0 }}>
          {children}
        </div>
      )}

      {/* Spacer — admin mode only */}
      {!isChatMode && <div style={{ flex: 1 }} />}

      {/* User footer */}
      {user && (
        <div style={{
          padding: '10px 12px 12px',
          borderTop: '1px solid var(--line)',
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
        }}>
          {isChatMode && <QuotaMeter pollInterval={30_000} isAdmin={isAdmin} />}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '2px 2px' }}>
            <div style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              background: 'var(--surface-2)',
              border: '1px solid var(--line)',
              display: 'grid',
              placeItems: 'center',
              fontWeight: 600,
              fontSize: 12.5,
              color: 'var(--ink-2)',
              flexShrink: 0,
              userSelect: 'none',
            }}>
              {initials}
            </div>
            <div style={{ flex: 1, minWidth: 0, lineHeight: 1.2 }}>
              <div style={{
                fontSize: 13,
                fontWeight: 600,
                color: 'var(--ink)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {user.display_name ?? user.email}
              </div>
              <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>{roleLabel}</div>
            </div>
            <button
              onClick={handleLogout}
              title="Sign out"
              style={{
                flexShrink: 0,
                padding: '5px 10px',
                borderRadius: 'var(--r-sm)',
                background: 'transparent',
                color: 'var(--ink-3)',
                border: '1px solid var(--line)',
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                fontSize: 12,
                cursor: 'pointer',
                transition: 'background 0.1s, color 0.1s',
              }}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-2)'; e.currentTarget.style.color = 'var(--ink)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--ink-3)' }}
            >
              <Ic.LogOut size={13} /> Sign out
            </button>
          </div>
        </div>
      )}
    </aside>
  )
}
