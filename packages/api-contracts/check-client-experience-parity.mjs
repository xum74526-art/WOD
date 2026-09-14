import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..', '..')

function source(relative) {
  return fs.readFileSync(path.join(root, relative), 'utf8')
}

// Keep this list focused on user-visible capabilities that are shared across
// Web, Android and iOS. Platform-only integrations do not belong here.
const commonCapabilities = [
  {
    name: 'registration captcha freshness',
    evidence: [
      {
        client: 'Web',
        file: 'apps/web/components/auth-panel.tsx',
        patterns: ['CAPTCHA_FRESHNESS_MS = 270_000', 'visibilitychange', 'captchaRefreshPromise'],
      },
      {
        client: 'Android',
        file: 'apps/android/src/pages/login/index.vue',
        patterns: ['CAPTCHA_FRESHNESS_MS = 270_000', 'syncCaptchaLifecycle(true)', 'captchaRefreshPromise'],
      },
      {
        client: 'iOS',
        file: 'apps/ios/src/pages/login/index.vue',
        patterns: ['CAPTCHA_FRESHNESS_MS = 270_000', 'syncCaptchaLifecycle(true)', 'captchaRefreshPromise'],
      },
    ],
  },
  {
    name: 'supplier quoted-request scope',
    evidence: [
      {
        client: 'Web',
        file: 'apps/web/components/mobile-buy-request-workspace.tsx',
        patterns: ['sellerScope === "quoted"', '我的报价', '暂无报价记录'],
      },
      {
        client: 'Web API',
        file: 'apps/web/lib/mobile-buy-request-api.ts',
        patterns: ['quoted_only=true'],
      },
      {
        client: 'Web locale',
        file: 'apps/web/components/locale-root.tsx',
        patterns: ['"全部需求": "All requests"', '"我的报价": "My quotes"', '"暂无报价记录": "No quote history"'],
      },
      {
        client: 'Android',
        file: 'apps/android/src/pages/buy-request/index.vue',
        patterns: ["sellerScope.value === 'quoted'", "t('myQuotes')", "'noQuotedRequests'"],
      },
      {
        client: 'Android API',
        file: 'apps/android/src/api/buy-request.ts',
        patterns: ['quoted_only: true'],
      },
      {
        client: 'Android locale',
        file: 'apps/android/src/store/i18n.ts',
        patterns: ["allRequests: '全部需求'", "allRequests: 'All Requests'", "noQuotedRequests: '暂无报价记录'"],
      },
      {
        client: 'iOS',
        file: 'apps/ios/src/pages/buy-request/index.vue',
        patterns: ["sellerScope.value === 'quoted'", "t('myQuotes')", "'noQuotedRequests'"],
      },
      {
        client: 'iOS API',
        file: 'apps/ios/src/api/buy-request.ts',
        patterns: ['quoted_only: true'],
      },
      {
        client: 'iOS locale',
        file: 'apps/ios/src/store/i18n.ts',
        patterns: ["allRequests: '全部需求'", "allRequests: 'All Requests'", "noQuotedRequests: '暂无报价记录'"],
      },
    ],
  },
  {
    name: 'recovery email binding',
    evidence: [
      {
        client: 'Web',
        file: 'apps/web/components/mobile-account-settings.tsx',
        patterns: [
          'getRecoveryEmailStatus()',
          'requestRecoveryEmailVerification(recoveryForm.email.trim(), recoveryForm.currentPassword)',
          'settings.recoveryEmailUnknown',
          'recoveryConfig?.email_enabled === false',
        ],
      },
      {
        client: 'Web API',
        file: 'apps/web/lib/api.ts',
        patterns: [
          '/api/v1/user/recovery-email',
          '/api/v1/user/recovery-email/request-verification',
        ],
      },
      {
        client: 'Android',
        file: 'apps/android/src/pages/recovery-email/index.vue',
        patterns: [
          'Promise.allSettled',
          'recoveryEmailServiceUnknown',
          'const submittedPassword = currentPassword.value',
          'onUnload(leavePage)',
        ],
      },
      {
        client: 'Android settings',
        file: 'apps/android/src/pages/settings/index.vue',
        patterns: [
          'getRecoveryEmailStatus(true)',
          "uni.$on('wod-session-changed', onSessionChanged)",
          "'recoveryEmailStatusUnavailable'",
        ],
      },
      {
        client: 'iOS',
        file: 'apps/ios/src/pages/recovery-email/index.vue',
        patterns: [
          'Promise.allSettled',
          'recoveryEmailServiceUnknown',
          'const submittedPassword = currentPassword.value',
          'onUnload(leavePage)',
        ],
      },
      {
        client: 'iOS settings',
        file: 'apps/ios/src/pages/settings/index.vue',
        patterns: [
          'getRecoveryEmailStatus(true)',
          "uni.$on('wod-session-changed', onSessionChanged)",
          "'recoveryEmailStatusUnavailable'",
        ],
      },
    ],
  },
]

const violations = []
for (const capability of commonCapabilities) {
  for (const item of capability.evidence) {
    let value
    try {
      value = source(item.file)
    } catch {
      violations.push(`${capability.name}: ${item.client} evidence file is missing (${item.file})`)
      continue
    }
    for (const pattern of item.patterns) {
      if (!value.includes(pattern)) {
        violations.push(`${capability.name}: ${item.client} is missing ${JSON.stringify(pattern)} in ${item.file}`)
      }
    }
  }
}

const mirroredMobileFiles = [
  'src/api/buy-request.ts',
  'src/pages/buy-request/index.vue',
  'tests/buy-request-seller-view.test.ts',
  'src/api/account-recovery.ts',
  'src/pages/recovery-email/index.vue',
  'tests/recovery-email-binding.test.ts',
]
for (const relative of mirroredMobileFiles) {
  const android = source(path.join('apps/android', relative)).replaceAll('\r\n', '\n')
  const ios = source(path.join('apps/ios', relative)).replaceAll('\r\n', '\n')
  if (android !== ios) violations.push(`shared mobile experience drifted: apps/android/${relative} differs from apps/ios/${relative}`)
}

if (violations.length) {
  console.error('Client experience parity check failed:')
  for (const violation of violations) console.error(`- ${violation}`)
  process.exit(1)
}

console.log(`Client experience parity check passed: ${commonCapabilities.length} shared capabilities cover Web, Android and iOS.`)
