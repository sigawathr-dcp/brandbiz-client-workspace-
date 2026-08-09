'use client'

import { useState } from 'react'
import ConsentModal from './ConsentModal'

interface ConsentGateProps {
  requiresConsent: boolean
  children: React.ReactNode
}

export default function ConsentGate({ requiresConsent, children }: ConsentGateProps) {
  const [showModal, setShowModal] = useState(requiresConsent)

  return (
    <>
      {showModal && <ConsentModal onAcknowledged={() => setShowModal(false)} />}
      {children}
    </>
  )
}
