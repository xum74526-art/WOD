export interface DeletionBlocker { code: string; message: string; count: number }
export interface DeletionEligibility { eligible: boolean; blockers: DeletionBlocker[]; automatic_actions: string[] }
export interface DeletionVerification { ticket: string; expires_at: string }
export interface DeletionResult {
  status: 'verified' | 'blocked' | 'processing' | 'completed'
  blockers: DeletionBlocker[]
  completed_at: string | null
}
export interface DeletionReceipt { ticket: string; expiresAt: number; ownerUserId?: number }
export const DELETION_RECEIPT_KEY = 'wod-account-deletion-capability-v1'
export const DELETION_RECEIPT_TTL_MS = 7 * 24 * 60 * 60 * 1000

/** This is a deletion-only capability credential, NOT an ordinary receipt ID.
 * Save only after final confirmation. ownerUserId isolates local session cleanup
 * and is NOT authorization. Never add passwords, login tokens or a user profile;
 * never put this value in URLs, diagnostics or analytics. */
export function validDeletionReceipt(value: unknown, now = Date.now()): DeletionReceipt | null {
  if (!value || typeof value !== 'object') return null
  const receipt = value as Partial<DeletionReceipt>
  if (typeof receipt.ticket !== 'string' || !receipt.ticket || receipt.ticket.length > 512) return null
  if (typeof receipt.expiresAt !== 'number' || !Number.isFinite(receipt.expiresAt)
    || receipt.expiresAt <= now || receipt.expiresAt > now + DELETION_RECEIPT_TTL_MS) return null
  const ownerUserId = typeof receipt.ownerUserId === 'number' && Number.isSafeInteger(receipt.ownerUserId) && receipt.ownerUserId > 0 ? receipt.ownerUserId : undefined
  return { ticket: receipt.ticket, expiresAt: receipt.expiresAt, ...(ownerUserId ? { ownerUserId } : {}) }
}

export function createDeletionState() {
  return {
    stage: 'review' as 'review' | 'uncertain' | DeletionResult['status'],
    eligibility: null as DeletionEligibility | null,
    blockers: [] as DeletionBlocker[],
    ticket: '',
    verificationExpiresAt: 0,
    completedAt: null as string | null,
    hasSubmitted: false,
    ownerUserId: undefined as number | undefined,
    busy: false,
  }
}

export function createDeletionController(options: {
  state: ReturnType<typeof createDeletionState>
  eligibility: () => Promise<DeletionEligibility>
  verify: (password: string) => Promise<DeletionVerification>
  submit: (ticket: string) => Promise<DeletionResult>
  status: (ticket: string) => Promise<DeletionResult>
  saveReceipt: (receipt: DeletionReceipt) => void
  clearReceipt: (ticket?: string) => void
  clearSession: (ownerUserId?: number) => void
  ownerUserId?: () => number | undefined
  now?: () => number
}) {
  const state = options.state
  const now = options.now || Date.now

  function accept(result: DeletionResult, requestTicket: string) {
    state.stage = result.status
    state.blockers = result.blockers
    state.completedAt = result.completed_at
    if (result.status === 'processing' || result.status === 'completed') options.clearSession(state.ownerUserId)
    if (result.status === 'completed') {
      state.ticket = ''
      options.clearReceipt(requestTicket)
    }
  }

  async function checkEligibility() {
    if (state.busy) return
    state.busy = true
    try {
      state.eligibility = await options.eligibility()
      state.blockers = state.eligibility.blockers
      state.stage = 'review'
      state.ticket = ''
      state.hasSubmitted = false
    } finally { state.busy = false }
  }

  async function verify(password: string) {
    if (state.busy || !state.eligibility?.eligible || !password) return
    state.busy = true
    try {
      state.ownerUserId = options.ownerUserId?.()
      const result = await options.verify(password)
      state.ticket = result.ticket
      state.verificationExpiresAt = Date.parse(result.expires_at)
      state.stage = 'verified'
    } finally { state.busy = false }
  }

  async function submit() {
    if (state.busy || state.stage !== 'verified' || !state.ticket) return
    // On restart the receipt contains no login/profile data or verification
    // timestamp. An explicit retry still uses the SAME capability; the server
    // remains the authority for its short submission lifetime.
    if (state.verificationExpiresAt && state.verificationExpiresAt <= now()) throw new Error('deletionVerificationExpired')
    state.busy = true
    try {
      // Persist immediately before the explicit submit so a timeout/restart
      // resumes STATUS only, never an automatic second deletion request.
      if (!state.hasSubmitted) options.saveReceipt({ ticket: state.ticket, expiresAt: now() + DELETION_RECEIPT_TTL_MS, ...(state.ownerUserId ? { ownerUserId: state.ownerUserId } : {}) })
      state.hasSubmitted = true
      state.stage = 'uncertain'
      const requestTicket = state.ticket
      accept(await options.submit(requestTicket), requestTicket)
    } finally { state.busy = false }
  }

  async function checkStatus() {
    if (state.busy || !state.ticket) return
    state.busy = true
    const requestTicket = state.ticket
    try { accept(await options.status(requestTicket), requestTicket) }
    finally { state.busy = false }
  }

  function restore(receipt: DeletionReceipt) {
    state.ticket = receipt.ticket
    state.stage = 'uncertain'
    state.hasSubmitted = true
    state.ownerUserId = receipt.ownerUserId
    // Recovery queries only. A separate final-confirmation gesture is required
    // to retry the same capability; never replay a request on startup.
    state.verificationExpiresAt = 0
  }

  return { checkEligibility, verify, submit, checkStatus, restore }
}
