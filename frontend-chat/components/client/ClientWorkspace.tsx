'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { errorDetail } from '@/lib/errorDetail'
import { readSSE } from '@/lib/sse'
import CaseMatchCards from './CaseMatchCards'
import ChatProgress from './ChatProgress'
import InsightCallout from './InsightCallout'
import IntakeChips from './IntakeChips'
import { CHAPTER_ORDER, deriveJourney, type ChapterId } from './journey'
import MilestoneTurn from './MilestoneTurn'
import NavRail from './NavRail'
import PlanDraftCard from './PlanDraftCard'
import ResearchStepper from './ResearchStepper'
import WorkPanel, { WorkTab } from './WorkPanel'
import { MarkdownContent } from '@/components/ui/Markdown'
import type {
  BootstrapData,
  CasesResult,
  Chip,
  CurrentStep,
  DraftPlan,
  IntakeAnswerResponse,
  IntakeField,
  PlanSummary,
  ResearchResult,
  Turn,
} from './types'

let _turnId = 0
function nextId() {
  _turnId += 1
  return `t${_turnId}`
}

// Client Workspaces (Phase 5, D21/D22) — the 3-column client chat shell:
// nav rail / chat column / work panel. Orchestrates the deterministic
// intake (POST /client/intake/answer), the market scan (POST
// /client/research), the case-library match (POST /client/cases), and
// free-form follow-up chat (POST /client/chat, SSE — same event contract as
// components/ChatPane.tsx's parser).
export default function ClientWorkspace() {
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [workspace, setWorkspace] = useState<BootstrapData['workspace'] | null>(null)
  const [agent, setAgent] = useState<BootstrapData['agent']>(null)
  const [isPreview, setIsPreview] = useState(false)
  const [internalAppEnabled, setInternalAppEnabled] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})
  const [intakeFields, setIntakeFields] = useState<IntakeField[]>([])

  const [turns, setTurns] = useState<Turn[]>([])
  const [currentStep, setCurrentStep] = useState<CurrentStep | null>(null)
  const [intakeCompleted, setIntakeCompleted] = useState(false)
  const [chipsHidden, setChipsHidden] = useState(false)
  const [busy, setBusy] = useState(false)
  const [step, setStep] = useState(0)
  // Hydrated from bootstrap before anything renders (the loading spinner
  // holds until then), so no intake length is assumed here.
  const [totalSteps, setTotalSteps] = useState(0)

  const [research, setResearch] = useState<ResearchResult | null>(null)
  const [researchStatus, setResearchStatus] = useState<'idle' | 'pending' | 'done' | 'error'>('idle')
  const [cases, setCases] = useState<CasesResult | null>(null)
  const [casesStatus, setCasesStatus] = useState<'idle' | 'pending' | 'done' | 'error'>('idle')
  const [tab, setTab] = useState<WorkTab>('profile')

  const [planDrafted, setPlanDrafted] = useState(false)
  // Task 5.12 — a seat can hold several plans (POST /client/plans always
  // creates a new one). `plans` is the full list (newest first, from
  // bootstrap or upserted on save); `activePlanId` is which one a "Save as
  // vN" revision targets and which the switcher checkmarks — DB redesign:
  // this is engagements.active_plan_id server-side now (POST /client/
  // plans/{id}/activate), not a per-device localStorage preference.
  const [plans, setPlans] = useState<PlanSummary[]>([])
  const [activePlanId, setActivePlanId] = useState<string | null>(null)
  const [planSwitcherOpen, setPlanSwitcherOpen] = useState(false)
  const [savingPlanId, setSavingPlanId] = useState<string | null>(null)
  const [savingProfile, setSavingProfile] = useState(false)
  const [workPanelOpen, setWorkPanelOpen] = useState(false)
  const [navRailOpen, setNavRailOpen] = useState(false)

  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState(false)

  const listRef = useRef<HTMLDivElement>(null)
  const conversationIdRef = useRef<string | null>(null)
  // Scroll targets for handleSelectChapter — one ref per rendered turn,
  // keyed by turn id, so "jump to the market scan" can find the last
  // research/cases/plan turn without threading extra state through the
  // turns array itself.
  const turnRefs = useRef<Map<string, HTMLDivElement>>(new Map())

  useEffect(() => {
    conversationIdRef.current = conversationId
  }, [conversationId])

  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [turns])

  // ---- Bootstrap ----------------------------------------------------------

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await fetch('/api/client/bootstrap', { credentials: 'include' })
        if (!res.ok) {
          if (cancelled) return
          setLoadError('Could not load your workspace. Please try the link again.')
          setLoading(false)
          return
        }
        const data: BootstrapData = await res.json()
        if (cancelled) return
        setWorkspace(data.workspace)
        setAgent(data.agent)
        setIsPreview(data.is_preview)
        setInternalAppEnabled(data.internal_app_enabled)
        setConversationId(data.conversation_id)
        setFields(data.fields)
        setIntakeFields(data.intake_fields ?? [])
        setIntakeCompleted(data.completed)
        setStep(data.step)
        setTotalSteps(data.total_steps)
        setPlans(data.plans)
        if (data.plans.length > 0) {
          // DB redesign — the server (engagements.active_plan_id) is now
          // the source of truth for which plan a revision targets, not a
          // per-device localStorage guess: a second device revising this
          // engagement now sees and affects the same plan.
          const initial = data.plans.find((p) => p.id === data.active_plan_id) ?? data.plans[0]
          setActivePlanId(initial.id)
        }

        if (!data.completed && data.current_step) {
          setTurns([{ id: nextId(), who: 'ai', kind: 'text', text: data.current_step.question }])
          setCurrentStep(data.current_step)
        } else if (data.completed) {
          // Replay whatever already ran so the "Your journey" chapters
          // (journey.ts) come back unlocked on reload instead of re-locking
          // Research/Cases and dropping the plan chapter — see
          // BootstrapOut.research_status's docstring on the backend. The
          // plan draft card itself isn't replayed (bootstrap doesn't carry
          // the plan body — see PlanOut.provenance et al on GET
          // /client/plans/{id}); handleSelectChapter routes to /w/plans/{id}
          // instead when there's no in-thread card to scroll to.
          //
          // Deliberately NOT forcing planDrafted=true here (Task 5.11 used
          // to): that permanently hid "Draft my plan" after any reload, so
          // a returning client could never draft plan #2. plans/activePlanId
          // above are enough for the journey/plan chapter to read "done".
          const welcomeTurns: Turn[] = [
            {
              id: nextId(),
              who: 'ai',
              kind: 'text',
              text: `Welcome back — your profile is complete. Ask ${data.agent?.name ?? 'น้องภูมิ'} anything, or pick up where you left off.`,
            },
          ]
          if (data.research_status !== 'idle') {
            setResearchStatus(data.research_status)
            setResearch(data.research)
            welcomeTurns.push({
              id: nextId(),
              who: 'ai',
              kind: 'research',
              text: '',
              researchStatus: data.research_status,
              research: data.research ?? undefined,
            })
          }
          if (data.cases_status !== 'idle') {
            setCasesStatus(data.cases_status)
            setCases(data.cases)
            welcomeTurns.push({
              id: nextId(),
              who: 'ai',
              kind: 'cases',
              text: '',
              casesStatus: data.cases_status,
              cases: data.cases ?? undefined,
            })
          }
          setTurns(welcomeTurns)
        }
        setLoading(false)
      } catch {
        if (!cancelled) {
          setLoadError('Network error — please refresh.')
          setLoading(false)
        }
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  // ---- Intake ---------------------------------------------------------------

  const appendTurn = useCallback((t: Omit<Turn, 'id'>) => {
    const turn: Turn = { ...t, id: nextId() }
    setTurns((prev) => [...prev, turn])
    return turn.id
  }, [])

  const answerIntake = useCallback(
    async (body: { option_index?: number; free_text?: string }, userLabel: string) => {
      if (busy) return
      setBusy(true)
      setChipsHidden(false)
      appendTurn({ who: 'user', kind: 'text', text: userLabel })
      try {
        const res = await fetch('/api/client/intake/answer', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(body),
        })
        if (!res.ok) {
          appendTurn({ who: 'ai', kind: 'text', text: 'Something went wrong recording that answer — please try again.' })
          return
        }
        const data: IntakeAnswerResponse = await res.json()
        setStep(data.step)
        setTotalSteps(data.total_steps)
        // Canonical, server-resolved fields — replaces the optimistic guess
        // handlePickChip used to make (which stored the Thai chip LABEL
        // while the server stores the English option VALUE) and fixes the
        // free-text path, which never updated the Profile tab at all.
        setFields(data.fields)
        if (data.completed) {
          setCurrentStep(null)
          setIntakeCompleted(true)
          appendTurn({
            who: 'sys',
            kind: 'milestone',
            text: '',
            milestone: {
              title: 'Interview complete',
              sub: `All ${data.total_steps} answers in · chapter 1 of ${CHAPTER_ORDER.length} complete`,
            },
          })
          appendTurn({
            who: 'ai',
            kind: 'text',
            text: data.completion_message ?? '',
            insight: data.insight ?? undefined,
          })
          void runResearchThenCases()
        } else {
          setCurrentStep(data.current_step)
          appendTurn({
            who: 'ai',
            kind: 'text',
            text: data.current_step?.question ?? '',
            insight: data.insight ?? undefined,
          })
        }
      } catch {
        appendTurn({ who: 'ai', kind: 'text', text: 'Network error — please try again.' })
      } finally {
        setBusy(false)
      }
    },
    [busy, appendTurn]
  )

  function handlePickChip(chip: Chip) {
    // No optimistic setFields here — answerIntake() replaces `fields` from
    // the server's canonical response once it lands (see its comment).
    void answerIntake({ option_index: chip.index }, chip.label)
  }

  function handleSkipChips() {
    setChipsHidden(true)
  }

  // ---- Research + cases -----------------------------------------------------

  const runResearchThenCases = useCallback(async () => {
    setTab('research')
    setWorkPanelOpen(true) // no-op on desktop — see .client-workpanel in globals.css
    setResearchStatus('pending')
    const researchTurnId = appendTurn({ who: 'ai', kind: 'research', text: '', researchStatus: 'pending' })
    try {
      const res = await fetch('/api/client/research', { method: 'POST', credentials: 'include' })
      if (!res.ok) throw new Error(await errorDetail(res, 'Could not run market research'))
      const data: ResearchResult = await res.json()
      setResearch(data)
      setResearchStatus('done')
      setTurns((prev) =>
        prev.map((t) => (t.id === researchTurnId ? { ...t, researchStatus: 'done', research: data } : t))
      )
      appendTurn({
        who: 'sys',
        kind: 'milestone',
        text: '',
        milestone: {
          title: 'Market intel unlocked',
          sub: `${data.citations.length} sources read · chapter 2 of ${CHAPTER_ORDER.length} complete`,
        },
      })
    } catch (err) {
      console.error('[client/research]', err)
      setResearchStatus('error')
      const message = err instanceof Error ? err.message : String(err)
      setTurns((prev) =>
        prev.map((t) => (t.id === researchTurnId ? { ...t, researchStatus: 'error', researchError: message } : t))
      )
    }

    setTab('cases')
    setCasesStatus('pending')
    const casesTurnId = appendTurn({ who: 'ai', kind: 'cases', text: '', casesStatus: 'pending' })
    try {
      const res = await fetch('/api/client/cases', { method: 'POST', credentials: 'include' })
      if (!res.ok) throw new Error(await errorDetail(res, 'Could not match case studies'))
      const data: CasesResult = await res.json()
      setCases(data)
      setCasesStatus('done')
      setTurns((prev) => prev.map((t) => (t.id === casesTurnId ? { ...t, casesStatus: 'done', cases: data } : t)))
      // A zero-match run must not celebrate — that's a real gap in front of
      // a live prospect, not a milestone.
      if (data.matches.length > 0) {
        appendTurn({
          who: 'sys',
          kind: 'milestone',
          text: '',
          milestone: {
            title: `${data.matches.length} matching cases found`,
            sub: `Case match complete · chapter 3 of ${CHAPTER_ORDER.length}`,
          },
        })
      }
    } catch (err) {
      console.error('[client/cases]', err)
      setCasesStatus('error')
      const message = err instanceof Error ? err.message : String(err)
      setTurns((prev) =>
        prev.map((t) => (t.id === casesTurnId ? { ...t, casesStatus: 'error', casesError: message } : t))
      )
    }
    // Deliberately left on the Cases tab (not snapped back to Profile) —
    // the client just watched the match run live and immediately losing
    // that tab read as the work disappearing. See handleSelectChapter for
    // the explicit "Case match" chapter nav that also lands here.
  }, [appendTurn])

  // ---- Plan (Phase 4) --------------------------------------------------------

  const runDraftPlan = useCallback(async ({ force = false }: { force?: boolean } = {}) => {
    if (planDrafted && !force) return
    setPlanDrafted(true)
    const planTurnId = appendTurn({ who: 'ai', kind: 'plan', text: '', planStatus: 'pending' })
    try {
      const res = await fetch('/api/client/plan/draft', { method: 'POST', credentials: 'include' })
      if (!res.ok) throw new Error(await errorDetail(res, 'Could not draft a plan'))
      const data: DraftPlan = await res.json()
      setTurns((prev) => prev.map((t) => (t.id === planTurnId ? { ...t, planStatus: 'done', plan: data } : t)))
      appendTurn({
        who: 'sys',
        kind: 'milestone',
        text: '',
        milestone: {
          title: 'Plan drafted',
          sub: `All ${CHAPTER_ORDER.length} chapters complete — save it to keep it`,
        },
      })
    } catch (err) {
      console.error('[plan/draft]', err)
      const message = err instanceof Error ? err.message : String(err)
      setTurns((prev) =>
        prev.map((t) => (t.id === planTurnId ? { ...t, planStatus: 'error', planError: message } : t))
      )
      setPlanDrafted(false)
    }
  }, [appendTurn, planDrafted])

  async function handleSavePlan(turnId: string, plan: DraftPlan, mode: 'revise' | 'new') {
    setSavingPlanId(turnId)
    setTurns((prev) => prev.map((t) => (t.id === turnId ? { ...t, planSaveError: undefined } : t)))
    // 'revise' only actually revises when there IS an active plan to PUT
    // onto — PlanDraftCard only offers that mode when one exists, but stay
    // defensive here rather than PUTting to a stale/absent id.
    const revising = mode === 'revise' && !!activePlanId
    try {
      const res = await fetch(revising ? `/api/client/plans/${activePlanId}` : '/api/client/plans', {
        method: revising ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          title: plan.title,
          core_idea: plan.core_idea,
          analogous_case: plan.analogous_case,
          adapted_plan: plan.adapted_plan,
          budget: plan.budget,
          provenance: plan.provenance,
          conversation_id: plan.conversation_id,
        }),
      })
      if (!res.ok) {
        const detail = await errorDetail(res, 'Could not save plan')
        console.error('[plans/save]', detail)
        setTurns((prev) => prev.map((t) => (t.id === turnId ? { ...t, planSaveError: detail } : t)))
        return
      }
      const saved: { id: string; title: string; version: number } = await res.json()
      setTurns((prev) => prev.map((t) => (t.id === turnId ? { ...t, planSaved: true, savedPlanId: saved.id } : t)))
      setPlans((prev) => {
        const summary: PlanSummary = { id: saved.id, title: saved.title, version: saved.version }
        const idx = prev.findIndex((p) => p.id === saved.id)
        if (idx === -1) return [summary, ...prev]
        const next = [...prev]
        next[idx] = summary
        return next
      })
      setActivePlanId(saved.id)
      // The backend's save_plan() already stamps engagements.active_plan_id
      // when this was a "Save as a new plan" (mode 'new'); for a revision
      // (mode 'revise') the active plan doesn't change, so no extra call
      // is needed either way — see app/services/plan.py::save_plan.
    } catch {
      setTurns((prev) => prev.map((t) => (t.id === turnId ? { ...t, planSaveError: 'Network error — please try again.' } : t)))
    } finally {
      setSavingPlanId(null)
    }
  }

  // ---- Profile edit -> resubmit (Task 5.11) ----------------------------------

  async function handleSaveProfile(
    updates: { field: string; option_index?: number; free_text?: string }[]
  ) {
    if (updates.length === 0 || savingProfile) return
    setSavingProfile(true)
    try {
      const res = await fetch('/api/client/intake/fields', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ updates }),
      })
      if (!res.ok) {
        console.error('[intake/fields]', await errorDetail(res, 'Could not save your profile'))
        return
      }
      const data: { fields: Record<string, string>; changed: string[]; completed: boolean } = await res.json()
      setFields(data.fields)
      if (data.changed.length === 0) return // nothing actually changed — no pipeline to re-run

      if (!data.completed) return // still mid-intake — the chat just continues at the current question

      // Intake was already complete, so research/cases/plan were built on
      // the OLD answers — re-run the whole pipeline so the plan the client
      // walks away with matches what they just corrected.
      appendTurn({
        who: 'sys',
        kind: 'milestone',
        text: '',
        milestone: { title: 'Profile updated', sub: 're-running your market scan and plan…' },
      })
      setResearchStatus('idle')
      setCasesStatus('idle')
      setPlanDrafted(false)
      await runResearchThenCases()
      await runDraftPlan({ force: true })
    } catch {
      console.error('[intake/fields] network error')
    } finally {
      setSavingProfile(false)
    }
  }

  // ---- Journey navigation ----------------------------------------------------

  // Jump to the last turn of a given kind — used by handleSelectChapter to
  // scroll the chat thread to whichever card a chapter click is about.
  function scrollToLastTurnOfKind(kind: Turn['kind']) {
    for (let i = turns.length - 1; i >= 0; i -= 1) {
      if (turns[i].kind === kind) {
        turnRefs.current.get(turns[i].id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        return true
      }
    }
    return false
  }

  function handleSelectChapter(id: ChapterId) {
    setNavRailOpen(false)
    if (id === 'interview') {
      setTab('profile')
      setWorkPanelOpen(true)
      listRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
      return
    }
    if (id === 'market') {
      setTab('research')
      setWorkPanelOpen(true)
      scrollToLastTurnOfKind('research')
      return
    }
    if (id === 'cases') {
      setTab('cases')
      setWorkPanelOpen(true)
      scrollToLastTurnOfKind('cases')
      return
    }
    // plan — no work-panel tab of its own; land on the plan card in the
    // thread, or the saved/plans list page when there's no card to scroll to
    // (e.g. right after a reload, where bootstrap doesn't replay the plan
    // draft turn — see the mount effect's comment on why).
    if (!scrollToLastTurnOfKind('plan')) {
      if (activePlanId) {
        window.location.href = `/w/plans/${activePlanId}`
      } else if (plans.length > 0) {
        window.location.href = '/w/plans'
      }
    }
  }

  // ---- Free-form chat (post-intake) ------------------------------------------

  async function sendChat(content: string) {
    if (!content.trim() || streaming) return
    setDraft('')
    appendTurn({ who: 'user', kind: 'text', text: content })
    const aiTurnId = appendTurn({ who: 'ai', kind: 'text', text: '', streaming: true })
    setStreaming(true)

    let full = ''
    try {
      const res = await fetch('/api/client/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ conversation_id: conversationIdRef.current, content }),
      })
      if (!res.ok) {
        const text = await res.text()
        setTurns((prev) => prev.map((t) => (t.id === aiTurnId ? { ...t, text: `Error: ${text}`, streaming: false } : t)))
        return
      }

      for await (const event of readSSE(res) as AsyncGenerator<{
        type: string
        conversation_id?: string
        delta?: string
        message?: string
      }>) {
        if (event.type === 'start' && event.conversation_id) {
          setConversationId(event.conversation_id)
        } else if (event.type === 'content' && event.delta) {
          full += event.delta
          const snapshot = full
          setTurns((prev) => prev.map((t) => (t.id === aiTurnId ? { ...t, text: snapshot } : t)))
        } else if (event.type === 'done') {
          setTurns((prev) => prev.map((t) => (t.id === aiTurnId ? { ...t, streaming: false } : t)))
        } else if (event.type === 'error') {
          setTurns((prev) =>
            prev.map((t) => (t.id === aiTurnId ? { ...t, text: `Error: ${event.message ?? 'Unknown error'}`, streaming: false } : t))
          )
        }
      }
    } catch {
      setTurns((prev) => prev.map((t) => (t.id === aiTurnId ? { ...t, text: 'Network error. Please try again.', streaming: false } : t)))
    } finally {
      setStreaming(false)
    }
  }

  function handleComposerKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      if (currentStep && !chipsHidden) return // must Skip first during intake
      void sendChat(draft)
    }
  }

  // ---- Render -----------------------------------------------------------

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: 'var(--bg)' }}>
        <div
          style={{
            width: 22,
            height: 22,
            borderRadius: '50%',
            border: '2.5px solid var(--line-2)',
            borderTopColor: 'var(--accent)',
            animation: 'spin 0.8s linear infinite',
          }}
        />
      </div>
    )
  }

  if (loadError || !workspace) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: 'var(--bg)', padding: 24 }}>
        <div style={{ fontSize: 14, color: 'var(--ink-2)' }}>{loadError || 'Something went wrong.'}</div>
      </div>
    )
  }

  const showChips = !!currentStep && !chipsHidden && !intakeCompleted
  const composerDisabled = (!!currentStep && !chipsHidden) || streaming || busy

  // Single fallback for the agent's display name/color — every other spot
  // that needs them reads from these two, never a separate hardcoded literal.
  const agentName = agent?.name ?? 'น้องภูมิ'
  const agentColor = agent?.avatar_color ?? 'var(--accent)'
  const agentInitial = agentName.trim().slice(0, 1).toUpperCase()
  const activePlan = plans.find((p) => p.id === activePlanId) ?? null

  const journey = deriveJourney({
    step,
    totalSteps,
    intakeCompleted,
    researchStatus,
    casesStatus,
    planDrafted,
    savedVersion: activePlan?.version ?? null,
    planCount: plans.length,
    agentName,
  })

  // Real capability counts, not the mockup's hardcoded claim — omit
  // whichever parts aren't true for this workspace's agent, and render
  // nothing at all rather than a stale-sounding subtitle.
  const agentSubtitleParts: string[] = []
  if (agent) {
    if (agent.skill_count > 0) {
      agentSubtitleParts.push(`${agent.skill_count} skill${agent.skill_count === 1 ? '' : 's'} pinned`)
    }
    if (agent.file_count > 0) agentSubtitleParts.push('case library attached')
    if (agent.web_search) agentSubtitleParts.push('web search on')
  }
  const agentSubtitle = agentSubtitleParts.length > 0 ? agentSubtitleParts.join(' · ') : null

  return (
    <div style={{ height: '100dvh', overflow: 'hidden', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
      {/* top bar */}
      <div
        className="client-topbar"
        style={{
          flex: 'none',
          background: 'var(--surface)',
          borderBottom: '1px solid var(--line)',
          display: 'flex',
          alignItems: 'center',
          gap: 14,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <div
            style={{
              width: 26,
              height: 26,
              borderRadius: 7,
              background: 'var(--accent)',
              color: '#fff',
              display: 'grid',
              placeItems: 'center',
              fontSize: 13,
              fontWeight: 700,
            }}
          >
            B
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-.01em', color: 'var(--ink)' }}>Brandbiz</div>
        </div>
        <div className="client-topbar-label" style={{ width: 1, height: 22, background: 'var(--line)' }} />
        <span
          className="client-topbar-label"
          style={{
            fontSize: 12,
            fontWeight: 500,
            color: 'var(--accent)',
            background: 'var(--accent-weak)',
            borderRadius: 99,
            padding: '3px 10px',
          }}
        >
          Client workspace
        </span>
        <span
          style={{
            fontSize: 12,
            color: 'var(--ink-2)',
            background: 'var(--surface-2)',
            border: '1px solid var(--line)',
            borderRadius: 99,
            padding: '3px 10px',
          }}
        >
          {workspace.name}
        </span>
        {isPreview && (
          <span
            style={{
              fontSize: 12,
              fontWeight: 500,
              color: 'var(--warn, #b45309)',
              background: 'var(--warn-weak, #fef3c7)',
              borderRadius: 99,
              padding: '3px 10px',
            }}
            title="You're clicking through as staff — nothing here becomes a real lead."
          >
            Preview mode
          </span>
        )}
        <div style={{ flex: 1 }} />
        {/* D21/D22: staff previewing always has internal access. D23: a
            real client seat gets the same link once internal_app_enabled
            is on — see app/routers/client.py::BootstrapOut. */}
        {(isPreview || internalAppEnabled) && (
          <a
            href="/chat"
            style={{
              fontSize: 12.5,
              fontWeight: 500,
              color: 'var(--ink-2)',
              textDecoration: 'none',
              marginRight: 4,
            }}
          >
            {isPreview ? 'Continue to internal app →' : 'Open the full AI workspace →'}
          </a>
        )}
        <button
          className="client-navrail-toggle"
          onClick={() => {
            setWorkPanelOpen(false)
            setNavRailOpen(true)
          }}
          aria-label="Open your journey"
          style={{
            alignItems: 'center',
            gap: 6,
            height: 30,
            padding: '0 12px',
            borderRadius: 8,
            border: '1px solid var(--line-2)',
            background: 'var(--surface)',
            color: 'var(--ink-2)',
            fontSize: 12.5,
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          {journey.pct}%
        </button>
        <button
          className="client-workpanel-toggle"
          onClick={() => {
            setNavRailOpen(false)
            setWorkPanelOpen(true)
          }}
          aria-label="Open profile, research and cases"
          style={{
            alignItems: 'center',
            gap: 6,
            height: 30,
            padding: '0 12px',
            borderRadius: 8,
            border: '1px solid var(--line-2)',
            background: 'var(--surface)',
            color: 'var(--ink-2)',
            fontSize: 12.5,
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          Profile
        </button>
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => {
              if (plans.length === 0) {
                window.location.href = '/w/plans'
                return
              }
              setPlanSwitcherOpen((open) => !open)
            }}
            style={{
              fontSize: 12.5,
              fontWeight: 500,
              color: plans.length > 0 ? 'var(--accent)' : 'var(--ink-4)',
              background: 'none',
              border: 'none',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              cursor: 'pointer',
              padding: 0,
            }}
          >
            My plans
            <span
              style={{
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
                background: 'var(--surface-2)',
                borderRadius: 99,
                padding: '1px 7px',
              }}
            >
              {plans.length}
            </span>
          </button>
          {planSwitcherOpen && plans.length > 0 && (
            <>
              <div
                onClick={() => setPlanSwitcherOpen(false)}
                style={{ position: 'fixed', inset: 0, zIndex: 20 }}
              />
              <div
                className="client-plan-switcher"
                style={{
                  position: 'absolute',
                  top: 'calc(100% + 8px)',
                  right: 0,
                  background: 'var(--surface)',
                  border: '1px solid var(--line)',
                  borderRadius: 10,
                  boxShadow: 'var(--shadow-2, var(--shadow-1))',
                  overflow: 'hidden',
                  zIndex: 21,
                }}
              >
                <div style={{ maxHeight: 260, overflowY: 'auto' }}>
                  {plans.map((p) => (
                    <div
                      key={p.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '9px 12px',
                        borderBottom: '1px solid var(--line)',
                        background: p.id === activePlanId ? 'var(--surface-2)' : 'transparent',
                      }}
                    >
                      <button
                        onClick={() => {
                          setActivePlanId(p.id)
                          setPlanSwitcherOpen(false)
                          // Server-side now, not localStorage — best-effort;
                          // a failed call just means the pick doesn't
                          // survive a reload, same degradation the old
                          // localStorage fallback had in private mode.
                          fetch(`/api/client/plans/${p.id}/activate`, { method: 'POST', credentials: 'include' }).catch(
                            () => {}
                          )
                        }}
                        style={{
                          flex: 1,
                          minWidth: 0,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 7,
                          background: 'none',
                          border: 'none',
                          textAlign: 'left',
                          cursor: 'pointer',
                          padding: 0,
                        }}
                      >
                        <span style={{ width: 12, flex: 'none', fontSize: 12, color: 'var(--accent)' }}>
                          {p.id === activePlanId ? '✓' : ''}
                        </span>
                        <span style={{ minWidth: 0, flex: 1, fontSize: 13, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {p.title}
                        </span>
                        <span style={{ flex: 'none', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--ink-3)' }}>
                          v{p.version}
                        </span>
                      </button>
                      <a
                        href={`/w/plans/${p.id}`}
                        aria-label={`Open ${p.title}`}
                        style={{ flex: 'none', color: 'var(--ink-3)', textDecoration: 'none', fontSize: 13 }}
                      >
                        ↗
                      </a>
                    </div>
                  ))}
                </div>
                <a
                  href="/w/plans"
                  style={{
                    display: 'block',
                    padding: '9px 12px',
                    fontSize: 12.5,
                    fontWeight: 500,
                    color: 'var(--accent)',
                    textDecoration: 'none',
                  }}
                >
                  View all plans →
                </a>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="client-grid" style={{ flex: 1, display: 'grid', minHeight: 0 }}>
        <div className={`client-navrail${navRailOpen ? ' open' : ''}`}>
          <NavRail
            journey={journey}
            planCount={plans.length}
            workspaceName={workspace.name}
            onSelectChapter={handleSelectChapter}
            onClose={() => setNavRailOpen(false)}
          />
        </div>

        {/* chat column */}
        <div style={{ display: 'flex', flexDirection: 'column', background: 'var(--bg)', minWidth: 0, minHeight: 0 }}>
          <div
            className="client-chat-header"
            style={{
              flex: 'none',
              height: 52,
              borderBottom: '1px solid var(--line)',
              background: 'var(--surface)',
              display: 'flex',
              alignItems: 'center',
              gap: 11,
            }}
          >
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: '50%',
                background: agentColor,
                color: '#fff',
                display: 'grid',
                placeItems: 'center',
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              {agentInitial}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13.5, fontWeight: 600, lineHeight: 1.25, color: 'var(--ink)' }}>
                {agentName} <span style={{ fontWeight: 400, color: 'var(--ink-3)' }}>· Brandbiz strategist</span>
              </div>
              {agentSubtitle && <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>{agentSubtitle}</div>}
            </div>
            <div style={{ flex: 1 }} />
            <ChatProgress journey={journey} />
          </div>

          <div ref={listRef} className="client-thread" style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
            {turns.map((t) => {
              if (t.who === 'sys' && t.milestone) {
                return (
                  <div key={t.id} ref={(el) => { if (el) turnRefs.current.set(t.id, el); else turnRefs.current.delete(t.id) }}>
                    <MilestoneTurn title={t.milestone.title} sub={t.milestone.sub} />
                  </div>
                )
              }
              return (
              <div
                key={t.id}
                ref={(el) => { if (el) turnRefs.current.set(t.id, el); else turnRefs.current.delete(t.id) }}
                style={
                  t.who === 'ai'
                    ? { display: 'flex', gap: 11, alignItems: 'flex-start' }
                    : { display: 'flex', justifyContent: 'flex-end' }
                }
              >
                {t.who === 'ai' && (
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      flex: 'none',
                      borderRadius: '50%',
                      background: agentColor,
                      color: '#fff',
                      display: 'grid',
                      placeItems: 'center',
                      fontSize: 12,
                      fontWeight: 600,
                    }}
                  >
                    {agentInitial}
                  </div>
                )}
                <div
                  style={
                    t.who === 'ai'
                      ? { maxWidth: 640, fontSize: 14.5, lineHeight: 1.62, color: 'var(--ink)' }
                      : {
                          maxWidth: 520,
                          background: 'var(--accent)',
                          color: '#fff',
                          borderRadius: '14px 14px 4px 14px',
                          padding: '10px 14px',
                          fontSize: 14.5,
                          lineHeight: 1.55,
                        }
                  }
                >
                  {t.insight && <InsightCallout text={t.insight} />}
                  {t.who === 'ai' && !t.streaming ? (
                    <MarkdownContent text={t.text} />
                  ) : (
                    <div style={{ whiteSpace: 'pre-wrap' }}>
                      {t.text}
                      {t.streaming && <span style={{ color: 'var(--accent)' }}>▍</span>}
                    </div>
                  )}
                  {t.kind === 'research' && (
                    <ResearchStepper
                      status={t.researchStatus ?? 'pending'}
                      result={t.research}
                      error={t.researchError}
                      showDetail={isPreview}
                    />
                  )}
                  {t.kind === 'cases' && (
                    <CaseMatchCards
                      status={t.casesStatus ?? 'pending'}
                      result={t.cases}
                      error={t.casesError}
                      showDetail={isPreview}
                    />
                  )}
                  {t.kind === 'plan' && (
                    <PlanDraftCard
                      status={t.planStatus ?? 'pending'}
                      plan={t.plan}
                      error={t.planError}
                      showDetail={isPreview}
                      saved={t.planSaved}
                      savedPlanId={t.savedPlanId}
                      saving={savingPlanId === t.id}
                      saveError={t.planSaveError}
                      onSave={(mode) => t.plan && handleSavePlan(t.id, t.plan, mode)}
                      agentName={agentName}
                      activePlan={
                        !t.planSaved && activePlan
                          ? { title: activePlan.title, nextVersion: activePlan.version + 1 }
                          : undefined
                      }
                    />
                  )}
                </div>
              </div>
              )
            })}
            <div style={{ height: 8, flex: 'none' }} />
          </div>

          {/* composer */}
          <div className="client-composer-wrap" style={{ flex: 'none', background: 'var(--bg)' }}>
            {intakeCompleted && casesStatus === 'done' && !planDrafted && (
              <div style={{ marginBottom: 10, display: 'flex' }}>
                <button
                  onClick={() => void runDraftPlan()}
                  style={{
                    height: 34,
                    padding: '0 14px',
                    borderRadius: 8,
                    border: '1px solid var(--line-2)',
                    background: 'var(--surface)',
                    color: 'var(--ink)',
                    fontSize: 13,
                    fontWeight: 500,
                    cursor: 'pointer',
                    boxShadow: 'var(--shadow-1)',
                  }}
                >
                  ทำเป็นแผนพร้อมงบประมาณให้เลยครับ · {plans.length > 0 ? 'Draft another plan' : 'Draft my plan'}
                </button>
              </div>
            )}
            {showChips && currentStep && (
              <IntakeChips
                title={currentStep.question}
                chips={currentStep.options}
                onPick={handlePickChip}
                onSkip={handleSkipChips}
                disabled={busy}
              />
            )}
            <div
              style={{
                display: 'flex',
                alignItems: 'flex-end',
                gap: 9,
                background: 'var(--surface)',
                border: '1px solid var(--line-2)',
                borderRadius: 12,
                padding: '9px 10px 9px 14px',
                boxShadow: 'var(--shadow-1)',
                opacity: composerDisabled ? 0.6 : 1,
              }}
            >
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={handleComposerKey}
                placeholder={showChips ? 'Or reply directly…' : `Message ${agentName}…`}
                disabled={composerDisabled}
                style={{
                  flex: 1,
                  border: 'none',
                  outline: 'none',
                  background: 'transparent',
                  fontSize: 14.5,
                  fontFamily: 'var(--font-sans)',
                  color: 'var(--ink)',
                  height: 28,
                }}
              />
              <button
                onClick={() => {
                  if (currentStep && !chipsHidden) {
                    if (!draft.trim()) return
                    void answerIntake({ free_text: draft }, draft.trim())
                    setDraft('')
                  } else {
                    void sendChat(draft)
                  }
                }}
                disabled={composerDisabled || !draft.trim()}
                style={{
                  width: 32,
                  height: 32,
                  flex: 'none',
                  borderRadius: 8,
                  border: 'none',
                  background: 'var(--accent)',
                  color: '#fff',
                  display: 'grid',
                  placeItems: 'center',
                  cursor: composerDisabled || !draft.trim() ? 'default' : 'pointer',
                }}
              >
                →
              </button>
            </div>
            <div style={{ marginTop: 8, fontSize: 11, color: 'var(--ink-4)' }}>
              Your answers stay inside your workspace.
            </div>
          </div>
        </div>

        <div className={`client-workpanel${workPanelOpen ? ' open' : ''}`}>
          <button
            className="client-workpanel-close"
            onClick={() => setWorkPanelOpen(false)}
            aria-label="Close"
            style={{
              width: 30,
              height: 30,
              borderRadius: 8,
              border: '1px solid var(--line-2)',
              background: 'var(--surface)',
              color: 'var(--ink-2)',
              cursor: 'pointer',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            ✕
          </button>
          <WorkPanel
            tab={tab}
            onTab={setTab}
            fields={fields}
            intakeFields={intakeFields}
            agentName={agentName}
            research={research}
            researchStatus={researchStatus}
            cases={cases}
            casesStatus={casesStatus}
            navigable={journey.navigable}
            onSaveProfile={handleSaveProfile}
            savingProfile={savingProfile}
          />
        </div>
      </div>
    </div>
  )
}
