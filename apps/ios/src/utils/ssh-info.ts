const SSH_ACCOUNT_RE = /([A-Za-z0-9._-]{1,64})@(\[[0-9A-Fa-f:]+\]|[A-Za-z0-9.-]{1,253})/
const SSH_HOST_RE = /^\s*(?:host|hostname|server|ip|主机|服务器|地址)\s*[:：]\s*(\[[0-9A-Fa-f:]+\]|[A-Za-z0-9.-]{1,253})\s*$/im
const SSH_USER_RE = /^\s*(?:user|username|login|用户|用户名)\s*[:：]\s*([A-Za-z0-9._-]{1,64})\s*$/im
const SSH_PORT_RE = /(?:^|\s)(?:-p\s+|port\s*[:：]\s*|端口\s*[:：]\s*)(\d{1,5})(?:\s|$)/im
const SSH_HOST_VALUE_RE = /^(?:[0-9A-Fa-f:.]+|(?:[A-Za-z0-9-]+\.)*[A-Za-z0-9-]+)$/

/** Mirror the API's syntax gate so free-form notes cannot be submitted as access credentials. */
export function isValidSshInfo(value: unknown): boolean {
  const plain = String(value ?? '').trim()
  if (!plain || plain.length > 2000) return false

  const account = SSH_ACCOUNT_RE.exec(plain)
  const host = account?.[2] || SSH_HOST_RE.exec(plain)?.[1]
  const user = account?.[1] || SSH_USER_RE.exec(plain)?.[1]
  if (!host || !user) return false

  const bareHost = host.replace(/^\[|\]$/g, '')
  if (bareHost.toLowerCase() === 'localhost' || bareHost.includes('/') || bareHost.includes('..')) return false
  if (!SSH_HOST_VALUE_RE.test(bareHost)) return false

  const port = SSH_PORT_RE.exec(plain)?.[1]
  return port == null || (Number(port) >= 1 && Number(port) <= 65535)
}
