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
  {
    name: 'follow-up request prefill',
    evidence: [
      {
        client: 'Web asset',
        file: 'apps/web/components/mobile-assets-workspace.tsx',
        patterns: ['requestCreateHref({ product_id: item.product_id', 'source: "existing_asset"', 'gpu_hours: 24'],
      },
      {
        client: 'Web order',
        file: 'apps/web/components/order-workspace.tsx',
        patterns: [
          'supplier_id: order.supplier_id',
          'seller_name: sellerCopy(order)',
          'source: order.market_source || order.seller_type || "existing_order"',
          'Number.isFinite(originalHours) && originalHours >= 1 ? originalHours : 24',
        ],
      },
      {
        client: 'Android asset',
        file: 'apps/android/src/pages/asset/detail.vue',
        patterns: ["source: 'existing_asset'", "current.gpu_model || current.product_name || 'GPU'", 'gpu_hours: 24'],
      },
      {
        client: 'Android order',
        file: 'apps/android/src/pages/order/detail.vue',
        patterns: [
          'supplier_id: current.supplier_id',
          "source: current.market_source || current.seller_type || 'existing_order'",
          'Number.isFinite(originalHours) && originalHours >= 1 ? originalHours : 24',
        ],
      },
      {
        client: 'iOS asset',
        file: 'apps/ios/src/pages/asset/detail.vue',
        patterns: ["source: 'existing_asset'", "current.gpu_model || current.product_name || 'GPU'", 'gpu_hours: 24'],
      },
      {
        client: 'iOS order',
        file: 'apps/ios/src/pages/order/detail.vue',
        patterns: [
          'supplier_id: current.supplier_id',
          "source: current.market_source || current.seller_type || 'existing_order'",
          'Number.isFinite(originalHours) && originalHours >= 1 ? originalHours : 24',
        ],
      },
    ],
  },
  {
    name: 'role-aware request navigation',
    evidence: [
      {
        client: 'Web',
        file: 'apps/web/components/product-shell.tsx',
        patterns: [
          '{ label: "求购与报价", href: "/account/requests"',
          '{ label: "需求市场", href: "/supplier/requests"',
          'variant === "supplier" && <Link href="/account"',
        ],
      },
      {
        client: 'Android',
        file: 'apps/android/src/config/profile-widgets.ts',
        patterns: [
          "key: 'request-market'",
          "route: '/pages/buy-request/index?view=seller'",
          "key: 'procurement'",
          "route: '/pages/buy-request/index'",
        ],
      },
      {
        client: 'iOS',
        file: 'apps/ios/src/config/profile-widgets.ts',
        patterns: [
          "key: 'request-market'",
          "route: '/pages/buy-request/index?view=seller'",
          "key: 'procurement'",
          "route: '/pages/buy-request/index'",
        ],
      },
    ],
  },
  {
    name: 'withdrawal unavailable feedback',
    evidence: [
      {
        client: 'Web',
        file: 'apps/web/components/mobile-supplier-operations.tsx',
        patterns: ['!wallet?.payment_service_enabled', '商家结算服务当前未启用', '不会创建模拟提现记录'],
      },
      {
        client: 'Android',
        file: 'apps/android/src/pages/supplier/revenue.vue',
        patterns: [
          '<DirectTradeSupplierWithdrawalAction v-if="commerce.withdrawEnabled" />',
          '<view v-else class="q-btn disabled">',
          "t('withdrawalUnavailableShort')",
        ],
      },
      {
        client: 'iOS',
        file: 'apps/ios/src/pages/supplier/revenue.vue',
        patterns: [
          '<DirectTradeSupplierWithdrawalAction v-if="commerce.withdrawEnabled" />',
          '<view v-else class="q-btn disabled">',
          "t('withdrawalUnavailableShort')",
        ],
      },
    ],
  },
  {
    name: 'homepage matchmaking wording',
    evidence: [
      {
        client: 'Web',
        file: 'apps/web/components/home-page-content.tsx',
        patterns: ['提交需求后由人工联系确认资源、价格和交付安排', '提交预计数量和时长', '人工确认'],
      },
      {
        client: 'Android',
        file: 'apps/android/src/store/i18n.ts',
        patterns: [
          "homePromoHourlyTitle: '按小时询价算力'",
          "homePromoHourlyDescription: '填写数量与时长，提交需求后沟通方案'",
          "homePromoHourlyTitle: 'Request Hourly Compute'",
          "homeNoticeHourly: 'Hourly compute requests are available'",
        ],
      },
      {
        client: 'iOS',
        file: 'apps/ios/src/store/i18n.ts',
        patterns: [
          "homePromoHourlyTitle: '按小时询价算力'",
          "homePromoHourlyDescription: '填写数量与时长，提交需求后沟通方案'",
          "homePromoHourlyTitle: 'Request Hourly Compute'",
          "homeNoticeHourly: 'Hourly compute requests are available'",
        ],
      },
    ],
  },
  {
    name: 'buy-request specification and note visibility',
    evidence: [
      {
        client: 'Web',
        file: 'apps/web/components/mobile-buy-request-workspace.tsx',
        patterns: [
          'gpu_variant: initialPrefill?.gpu_variant || undefined',
          'note: additionalRequirements',
          'remark: additionalRequirements',
          'buyRequestAdditionalRequirements(detail?.request.requirements)',
          'row.gpu_variant ? ` ${row.gpu_variant}` : ""',
          'detail.request.gpu_variant ? ` ${detail.request.gpu_variant}` : ""',
        ],
      },
      {
        client: 'Web admin',
        file: 'apps/web/components/admin-buy-request-workspace.tsx',
        patterns: [
          'buyRequestAdditionalRequirements(detail?.request.requirements)',
          'detailRequirementNote && <div className="workspace-service-note"',
        ],
      },
      {
        client: 'Android',
        file: 'apps/android/src/pages/buy-request/index.vue',
        patterns: [
          'gpu_variant: form.gpu_variant || undefined',
          'note: additionalRequirements',
          'remark: additionalRequirements',
          'maxlength="1000"',
          'buyRequestAdditionalRequirements(detail.value?.request.requirements)',
          'v-if="detailRequirementNote"',
        ],
      },
      {
        client: 'iOS',
        file: 'apps/ios/src/pages/buy-request/index.vue',
        patterns: [
          'gpu_variant: form.gpu_variant || undefined',
          'note: additionalRequirements',
          'remark: additionalRequirements',
          'maxlength="1000"',
          'buyRequestAdditionalRequirements(detail.value?.request.requirements)',
          'v-if="detailRequirementNote"',
        ],
      },
      {
        client: 'Canonical API',
        file: 'services/api/app/routers/buy_request.py',
        patterns: [
          'requirements: dict | None = None',
          'requirements = _response_requirements(requirements)',
          '_request_gpu_variant(item.gpu_variant, requirements)',
          '_comparable_requirements(item.requirements, item_gpu_variant)',
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
  'src/config/profile-widgets.ts',
  'tests/profile-widgets.test.ts',
  'src/config/home-promotions.ts',
  'src/components/HomePromoCarousel.vue',
  'src/utils/buy-request-requirements.ts',
  'src/api/revenue.ts',
  'src/pages/asset/detail.vue',
  'src/utils/asset-detail-requests.ts',
  'tests/asset-detail-resilience.test.ts',
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
