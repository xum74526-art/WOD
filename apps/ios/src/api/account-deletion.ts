import { request } from '@/api/request'
import type { DeletionEligibility, DeletionResult, DeletionVerification } from '@/utils/account-deletion'

export function getDeletionEligibility(): Promise<DeletionEligibility> {
  return request({ url: '/user/account-deletion/eligibility', silent: true })
}

export function verifyDeletionPassword(password: string): Promise<DeletionVerification> {
  return request({ url: '/user/account-deletion/verify', method: 'POST', data: { password }, silent: true })
}

export function submitAccountDeletion(ticket: string): Promise<DeletionResult> {
  return request({ url: '/user/account-deletion/submit', method: 'POST', data: { ticket, confirm: true }, auth: 'none', silent: true })
}

export function getDeletionStatus(ticket: string): Promise<DeletionResult> {
  return request({ url: '/user/account-deletion/status', method: 'POST', data: { ticket }, auth: 'none', silent: true })
}
