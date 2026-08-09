// Client Workspaces redesign (PLAN.md Task 5.10) — single source of truth
// for "where is this client in the four-chapter journey", consumed by
// NavRail, ChatProgress, and WorkPanel's tab locks. Everything here is a
// pure function of state ClientWorkspace.tsx already holds; no component
// should compute a stage/lock/percentage ternary of its own.

export type RunStatus = 'idle' | 'pending' | 'done' | 'error'
export type StageState = 'done' | 'current' | 'locked'
export type ChapterId = 'interview' | 'market' | 'cases' | 'plan'

export interface JourneyInput {
  step: number
  totalSteps: number
  intakeCompleted: boolean
  researchStatus: RunStatus
  casesStatus: RunStatus
  planDrafted: boolean
  savedVersion: number | null
}

export interface JourneyStage {
  id: ChapterId
  name: string
  state: StageState
  note: string
}

export interface JourneyReward {
  id: 'intel' | 'cases' | 'plan'
  label: string
  note: string
  unlocked: boolean
}

export interface Journey {
  pct: number
  chapterLabel: string
  answered: number
  totalSteps: number
  stages: JourneyStage[]
  rewards: JourneyReward[]
  pips: ('done' | 'current' | 'future')[]
  headerHint: string
  researchLocked: boolean
  casesLocked: boolean
}

const CHAPTER_NAMES: Record<ChapterId, string> = {
  interview: 'Interview',
  market: 'Market scan',
  cases: 'Case match',
  plan: 'Plan & budget',
}

export function deriveJourney(input: JourneyInput): Journey {
  const {
    step, totalSteps, intakeCompleted,
    researchStatus, casesStatus,
    planDrafted, savedVersion,
  } = input

  const total = Math.max(1, totalSteps)
  const answered = Math.min(step, total)

  const interviewDone = intakeCompleted || answered >= total
  const researchDone = researchStatus === 'done'
  const casesDone = casesStatus === 'done'
  const planSaved = savedVersion !== null

  const pct = Math.round(
    (answered / total) * 25 +
    (researchDone ? 25 : 0) +
    (casesDone ? 25 : 0) +
    (planSaved ? 25 : 0)
  )

  // Exactly one 'current' stage at a time: everything before it is 'done',
  // everything after is 'locked'. An 'error' run renders its stage as
  // 'current' (with a retry note) rather than 'done' — a failed scan must
  // not light the matching reward.
  const doneFlags: Record<ChapterId, boolean> = {
    interview: interviewDone,
    market: researchDone,
    cases: casesDone,
    plan: planSaved,
  }
  const order: ChapterId[] = ['interview', 'market', 'cases', 'plan']
  let currentId: ChapterId | null = order.find((id) => !doneFlags[id]) ?? null

  const stageNote = (id: ChapterId, state: StageState): string => {
    if (id === 'interview') {
      if (state === 'done') return `${answered} / ${total} answered`
      if (state === 'current') return `${answered} / ${total} answered`
      return 'Locked'
    }
    if (id === 'market') {
      if (state === 'done') return 'Market scan complete'
      if (state === 'current') return researchStatus === 'error' ? "Couldn't run — ask น้องภูมิ to retry" : 'Scanning now…'
      return 'Locked'
    }
    if (id === 'cases') {
      if (state === 'done') return 'Cases matched'
      if (state === 'current') return casesStatus === 'error' ? "Couldn't run — ask น้องภูมิ to retry" : 'Matching now…'
      return 'Locked'
    }
    // plan
    if (state === 'done') return `Saved as v${savedVersion}`
    if (state === 'current') return planDrafted ? 'Save it to finish' : 'Ready to draft'
    return 'Locked'
  }

  const stages: JourneyStage[] = order.map((id) => {
    const state: StageState = doneFlags[id] ? 'done' : id === currentId ? 'current' : 'locked'
    return { id, name: CHAPTER_NAMES[id], state, note: stageNote(id, state) }
  })

  const rewards: JourneyReward[] = [
    { id: 'intel', label: 'Market intel report', note: 'Findings + cited sources', unlocked: researchDone },
    { id: 'cases', label: 'Matched case studies', note: 'From the Brandbiz library', unlocked: casesDone },
    { id: 'plan', label: 'Costed plan + budget', note: 'Priced off the real rate card', unlocked: planSaved },
  ]

  const pips: ('done' | 'current' | 'future')[] = Array.from({ length: total }, (_, i) =>
    i < answered ? 'done' : i === answered ? 'current' : 'future'
  )

  let headerHint: string
  if (!interviewDone) {
    headerHint = `${total - answered} to go before the market scan unlocks`
  } else if (!researchDone) {
    headerHint = 'Scanning the market…'
  } else if (!casesDone) {
    headerHint = 'Next: match your case'
  } else if (!planSaved) {
    headerHint = 'Final chapter: your plan'
  } else {
    headerHint = 'Plan saved'
  }

  const chapterLabel = currentId === null
    ? 'All chapters complete'
    : `Chapter ${order.indexOf(currentId) + 1} · ${CHAPTER_NAMES[currentId]}`

  return {
    pct: Math.min(100, Math.max(0, pct)),
    chapterLabel,
    answered,
    totalSteps: total,
    stages,
    rewards,
    pips,
    headerHint,
    researchLocked: researchStatus === 'idle',
    casesLocked: casesStatus === 'idle',
  }
}
