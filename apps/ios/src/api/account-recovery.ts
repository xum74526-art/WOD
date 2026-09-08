import { request } from './request'

export { getAccountRecoveryConfig, type AccountRecoveryConfig } from './user'

export function requestPasswordReset(email: string) {
  return request<{ accepted: boolean; message: string }>({
    url: '/auth/email/password-reset/request',
    method: 'POST',
    data: { email },
    auth: 'none',
    silent: true,
  })
}

export function confirmPasswordReset(token: string, password: string) {
  return request<{ reset: boolean }>({
    url: '/auth/email/password-reset/confirm',
    method: 'POST',
    data: { token, password },
    auth: 'none',
    silent: true,
  })
}
