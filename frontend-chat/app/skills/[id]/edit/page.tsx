'use client'

import { use } from 'react'
import SkillForm from '@/components/skills/SkillForm'

export default function EditSkillPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return <SkillForm skillId={id} />
}
