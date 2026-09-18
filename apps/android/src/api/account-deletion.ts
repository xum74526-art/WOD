import { request } from '@/api/request'
import type { DeletionEligibility, DeletionResult, DeletionVerification } from '@/utils/account-deletion'
import { KAI_AUTH_APP_RETURN_URL } from '@/utils/kai-auth-callback'

export function getDeletionEligibility(): Promise<DeletionEligibility> {
  return request({ url: '/user/account-deletion/eligibility', silent: true })
}

export function verifyDeletionPassword(password: string): Promise<DeletionVerification> {
  return request({ url: '/user/account-deletion/verify', method: 'POST', data: { password }, silent: true })
}

export function startDeletionKaiReauth(): Promise<{ authorization_url: string }> {
  return request({
    url: '/user/account-deletion/kai/start', method: 'POST',
    data: { return_url: KAI_AUTH_APP_RETURN_URL }, silent: true,
  })
}

export function verifyDeletionKai(token: string): Promise<DeletionVerification> {
  return request({
    url: '/user/account-deletion/kai/verify', method: 'POST', data: { token }, silent: true,
  })
}

export function submitAccountDeletion(ticket: string): Promise<DeletionResult> {
  return request({ url: '/user/account-deletion/submit', method: 'POST', data: { ticket, confirm: true }, auth: 'none', silent: true })
}

export function getDeletionStatus(ticket: string): Promise<DeletionResult> {
  return request({ url: '/user/account-deletion/status', method: 'POST', data: { ticket }, auth: 'none', silent: true })
}
