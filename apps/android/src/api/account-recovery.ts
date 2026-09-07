import { request } from './request'

export interface RecoveryEmailStatus {
  email: string | null
  verified: boolean
}

export interface RecoveryEmailVerificationResult {
  accepted: boolean
  already_verified: boolean
}

export interface AccountRecoveryConfig {
  email_enabled: boolean
  kai_enabled: boolean
  reset_ttl_seconds: number
}

export function getAccountRecoveryConfig() {
  return request<AccountRecoveryConfig>({
    url: '/auth/recovery/config',
    auth: 'none',
    silent: true,
  })
}

export function getRecoveryEmailStatus(silent = true) {
  return request<RecoveryEmailStatus>({
    url: '/user/recovery-email',
    silent,
  })
}

export function requestRecoveryEmailVerification(email: string, currentPassword: string) {
  return request<RecoveryEmailVerificationResult>({
    url: '/user/recovery-email/request-verification',
    method: 'POST',
    data: { email, current_password: currentPassword },
    silent: true,
  })
}
