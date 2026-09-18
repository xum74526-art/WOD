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
    name: 'GPU image rights disclosure',
    evidence: [
      {
        client: 'Web attribution page',
        file: 'apps/web/app/image-attributions/image-attributions-content.tsx',
        patterns: ['RTX2060.jpg', 'RTX5080.jpg', 'sourceUrl:', 'licenseUrl:', 'directly licensed for use'],
      },
      {
        client: 'Web footer entry',
        file: 'apps/web/components/site-footer.tsx',
        patterns: ['href="/image-attributions"', 'footer.imageAttributions'],
      },
      ...['android', 'ios'].flatMap(client => [
        {
          client: `${client} attribution data`,
          file: `apps/${client}/src/config/image-attributions.ts`,
          patterns: ['RTX2060.jpg', 'RTX5080.jpg', 'sourceUrl:', 'licenseUrl:', 'modificationKey:', 'aliases:'],
        },
        {
          client: `${client} attribution page`,
          file: `apps/${client}/src/pages/image-attributions/index.vue`,
          patterns: ['IMAGE_ATTRIBUTIONS', 'imageAttributionsDirectRightsDescription', 'openExternalLink'],
        },
        {
          client: `${client} settings entry`,
          file: `apps/${client}/src/pages/settings/index.vue`,
          patterns: ["nav('/pages/image-attributions/index')", "t('imageAttributionsTitle')"],
        },
      ]),
    ],
  },
  {
    name: 'idempotent community likes',
    evidence: [
      {
        client: 'Web API',
        file: 'apps/web/lib/mobile-community-api.ts',
        patterns: ['setCommunityLike(id: number, liked: boolean)', 'JSON.stringify({ liked })', 'retryIdempotentMutationOnce(submit)'],
      },
      {
        client: 'Web',
        file: 'apps/web/components/community-feed.tsx',
        patterns: ['const targetLiked = !row.is_liked', 'setCommunityLike(row.id, targetLiked)', 'is_liked: result.liked'],
      },
      {
        client: 'Android API',
        file: 'apps/android/src/api/community.ts',
        patterns: ['setLike(id: number, liked: boolean)', 'data: { liked }', 'retryUncertainOnce: true'],
      },
      {
        client: 'Android list',
        file: 'apps/android/src/pages/community/index.vue',
        patterns: ['likeInFlight.has(d.id)', 'setLike(d.id, targetLiked)', 'list.value.find(item => item.id === d.id)', 'likeInFlight.delete(d.id)'],
      },
      {
        client: 'Android detail',
        file: 'apps/android/src/pages/community/detail.vue',
        patterns: ['!post.value || likeInFlight', 'setLike(pid.value, targetLiked)', 'likeInFlight = false'],
      },
      {
        client: 'iOS API',
        file: 'apps/ios/src/api/community.ts',
        patterns: ['setLike(id: number, liked: boolean)', 'data: { liked }', 'retryUncertainOnce: true'],
      },
      {
        client: 'iOS list',
        file: 'apps/ios/src/pages/community/index.vue',
        patterns: ['likeInFlight.has(d.id)', 'setLike(d.id, targetLiked)', 'list.value.find(item => item.id === d.id)', 'likeInFlight.delete(d.id)'],
      },
      {
        client: 'iOS detail',
        file: 'apps/ios/src/pages/community/detail.vue',
        patterns: ['!post.value || likeInFlight', 'setLike(pid.value, targetLiked)', 'likeInFlight = false'],
      },
    ],
  },
  {
    name: 'idempotent community follows',
    evidence: [
      {
        client: 'Web API',
        file: 'apps/web/lib/mobile-community-api.ts',
        patterns: ['setCommunityFollow(id: number, following: boolean)', 'JSON.stringify({ following })', 'retryIdempotentMutationOnce(submit)'],
      },
      {
        client: 'Web',
        file: 'apps/web/components/community-feed.tsx',
        patterns: ['const action = `follow-${row.user_id}`', 'const targetFollowing = !row.is_following', 'setCommunityFollow(row.user_id, targetFollowing)'],
      },
      {
        client: 'Android API',
        file: 'apps/android/src/api/community.ts',
        patterns: ['setFollow(uid: number, following: boolean)', 'data: { following }', 'retryUncertainOnce: true'],
      },
      {
        client: 'Android list',
        file: 'apps/android/src/pages/community/index.vue',
        patterns: ['followInFlight.has(d.user_id)', 'setFollow(d.user_id, targetFollowing)', 'followInFlight.delete(d.user_id)'],
      },
      {
        client: 'Android detail',
        file: 'apps/android/src/pages/community/detail.vue',
        patterns: ['!post.value || followInFlight', 'setFollow(post.value.user_id, targetFollowing)', 'followInFlight = false'],
      },
      {
        client: 'iOS API',
        file: 'apps/ios/src/api/community.ts',
        patterns: ['setFollow(uid: number, following: boolean)', 'data: { following }', 'retryUncertainOnce: true'],
      },
      {
        client: 'iOS list',
        file: 'apps/ios/src/pages/community/index.vue',
        patterns: ['followInFlight.has(d.user_id)', 'setFollow(d.user_id, targetFollowing)', 'followInFlight.delete(d.user_id)'],
      },
      {
        client: 'iOS detail',
        file: 'apps/ios/src/pages/community/detail.vue',
        patterns: ['!post.value || followInFlight', 'setFollow(post.value.user_id, targetFollowing)', 'followInFlight = false'],
      },
    ],
  },
  {
    name: 'idempotent community comments',
    evidence: [
      {
        client: 'Web API',
        file: 'apps/web/lib/mobile-community-api.ts',
        patterns: ['createCommunityComment(id: number, content: string, clientRequestId: string)', 'client_request_id: clientRequestId', 'retryIdempotentMutationOnce(submit)'],
      },
      {
        client: 'Web',
        file: 'apps/web/components/community-feed.tsx',
        patterns: ['ensureCommunityCommentIntent(', 'pendingCommentIntents.current.set(id, intent)', 'item.id !== result.id', 'result.post_comments'],
      },
      {
        client: 'Android API',
        file: 'apps/android/src/api/community.ts',
        patterns: ['createComment(id: number, content: string, client_request_id: string)', 'data: { content, client_request_id }', 'retryUncertainOnce: true'],
      },
      {
        client: 'Android detail',
        file: 'apps/android/src/pages/community/detail.vue',
        patterns: ['!postId || !content || commentInFlight', 'ensureClientRequestIntent(', 'createComment(postId, content, intent.requestId)', 'item.id !== c.id', 'c.post_comments'],
      },
      {
        client: 'iOS API',
        file: 'apps/ios/src/api/community.ts',
        patterns: ['createComment(id: number, content: string, client_request_id: string)', 'data: { content, client_request_id }', 'retryUncertainOnce: true'],
      },
      {
        client: 'iOS detail',
        file: 'apps/ios/src/pages/community/detail.vue',
        patterns: ['!postId || !content || commentInFlight', 'ensureClientRequestIntent(', 'createComment(postId, content, intent.requestId)', 'item.id !== c.id', 'c.post_comments'],
      },
    ],
  },
  {
    name: 'community safety controls',
    evidence: [
      {
        client: 'Web API',
        file: 'apps/web/lib/mobile-community-api.ts',
        patterns: ['allow_aggregated: "false"', 'reportCommunityContent(', 'setCommunityBlock(', 'deleteCommunityPost(', 'deleteCommunityComment('],
      },
      {
        client: 'Web',
        file: 'apps/web/components/community-feed.tsx',
        patterns: ['reportCommunityContent("post", row.id)', 'reportCommunityContent("comment", commentItem.id)', 'reportCommunityContent("user", commentItem.user_id)', 'setCommunityBlock(row.user_id, true)', 'setCommunityBlock(commentItem.user_id, true)', 'deleteCommunityPost(row.id)', 'deleteCommunityComment(commentItem.id)'],
      },
      ...['android', 'ios'].flatMap(client => [
        {
          client: `${client} API`,
          file: `apps/${client}/src/api/community.ts`,
          patterns: ['allow_aggregated: false', 'reportCommunityContent(', 'setUserBlock(', 'deleteCommunityPost(', 'deleteCommunityComment('],
        },
        {
          client: `${client} detail`,
          file: `apps/${client}/src/pages/community/detail.vue`,
          patterns: ["reportTarget('post'", "reportTarget('comment'", "reportTarget('user'", 'setUserBlock(userId, true)', 'deleteCommunityPost(currentPost.id)', 'deleteCommunityComment(comment.id)'],
        },
      ]),
      {
        client: 'Canonical API',
        file: 'services/api/app/routers/community.py',
        patterns: ['allow_aggregated: bool = False', 'def report_community_content(', 'def set_user_block(', 'def delete_own_post(', 'def delete_own_comment('],
      },
      {
        client: 'Admin review queue',
        file: 'services/api/app/routers/admin.py',
        patterns: ['def community_reports(', 'def review_community_report('],
      },
    ],
  },
  {
    name: 'KAI reauthentication for account deletion',
    evidence: [
      {
        client: 'Web API',
        file: 'apps/web/lib/account-deletion-api.ts',
        patterns: ['/user/account-deletion/kai/start', '/user/account-deletion/kai/verify', 'body: JSON.stringify({ token })'],
      },
      {
        client: 'Web',
        file: 'apps/web/components/account-deletion.tsx',
        patterns: ['deletionKaiProofFromUrl(window.location.href)', 'setAcknowledged(false)', 'verifyKaiAccountDeletion(kaiCallback.token)', 'startKaiAccountDeletionVerification()'],
      },
      ...['android', 'ios'].flatMap(client => [
        {
          client: `${client} API`,
          file: `apps/${client}/src/api/account-deletion.ts`,
          patterns: ['/user/account-deletion/kai/start', '/user/account-deletion/kai/verify', 'KAI_AUTH_APP_RETURN_URL'],
        },
        {
          client: `${client} deletion page`,
          file: `apps/${client}/src/pages/account-deletion/index.vue`,
          patterns: ['beginDeletionKaiReauth()', 'takePendingDeletionKaiCallback()', 'controller.verifyKai(callback.token)', 'acknowledged.value = false'],
        },
      ]),
      {
        client: 'Canonical deletion API',
        file: 'services/api/app/routers/account_deletion.py',
        patterns: ['@router.post("/kai/start"', '@router.post("/kai/verify"', 'verify_deletion_kai(db, user, data.token)'],
      },
      {
        client: 'Canonical KAI callback',
        file: 'services/api/app/routers/auth.py',
        patterns: ['expected_user_id=flow.user_id if flow.intent == "delete" else None', 'issue_kai_reauth_token(db, user)', 'kai_deletion_token=deletion_token'],
      },
    ],
  },
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
          'recoveryEmail?.current_password_required === false ? undefined : recoveryForm.currentPassword',
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
          'const passwordRequired = computed(() => status.value?.current_password_required !== false)',
          'const submittedPassword = passwordRequired.value ? currentPassword.value : undefined',
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
          'const passwordRequired = computed(() => status.value?.current_password_required !== false)',
          'const submittedPassword = passwordRequired.value ? currentPassword.value : undefined',
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
    name: 'Kai-first phone login setup',
    evidence: [
      {
        client: 'Web',
        file: 'apps/web/components/mobile-account-settings.tsx',
        patterns: [
          'getLoginPhoneStatus()',
          'configureLoginPhone(loginPhoneForm.phone, loginPhoneForm.password)',
          'settings.loginPhoneNotice',
          '未经过短信核验',
        ],
      },
      {
        client: 'Web API',
        file: 'apps/web/lib/api.ts',
        patterns: [
          'getLoginPhoneStatus()',
          'configureLoginPhone(phone: string, password: string)',
          '"/api/v1/user/login-phone"',
        ],
      },
      {
        client: 'Android API',
        file: 'apps/android/src/api/user.ts',
        patterns: [
          'getPhoneLoginStatus(silent = true)',
          'configurePhoneLogin(phone: string, password: string)',
          "url: '/user/login-phone'",
        ],
      },
      {
        client: 'Android settings',
        file: 'apps/android/src/pages/settings/index.vue',
        patterns: [
          'getPhoneLoginStatus(true)',
          "nav('/pages/login-phone/index')",
        ],
      },
      {
        client: 'Android setup',
        file: 'apps/android/src/pages/login-phone/index.vue',
        patterns: [
          'configurePhoneLogin(phone.value.trim(), submittedPassword)',
          "'phoneLoginExpired'",
          'phoneLoginSavedMessage',
        ],
      },
      {
        client: 'iOS API',
        file: 'apps/ios/src/api/user.ts',
        patterns: [
          'getPhoneLoginStatus(silent = true)',
          'configurePhoneLogin(phone: string, password: string)',
          "url: '/user/login-phone'",
        ],
      },
      {
        client: 'iOS settings',
        file: 'apps/ios/src/pages/settings/index.vue',
        patterns: [
          'getPhoneLoginStatus(true)',
          "nav('/pages/login-phone/index')",
        ],
      },
      {
        client: 'iOS setup',
        file: 'apps/ios/src/pages/login-phone/index.vue',
        patterns: [
          'configurePhoneLogin(phone.value.trim(), submittedPassword)',
          "'phoneLoginExpired'",
          'phoneLoginSavedMessage',
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
  {
    name: 'safe post-authentication return navigation',
    evidence: [
      {
        client: 'Web gate',
        file: 'apps/web/components/product-shell.tsx',
        patterns: ['loginHref(locationReturnPath(window.location))'],
      },
      {
        client: 'Web login',
        file: 'apps/web/components/auth-panel.tsx',
        patterns: ['normalizeReturnPath(requestedReturnTo)', 'window.location.assign(destination)'],
      },
      {
        client: 'Android request',
        file: 'apps/android/src/api/request.ts',
        patterns: ['getToken() !== requestToken', 'stageAuthReturnPath()', 'expireSession(i18n, token)'],
      },
      {
        client: 'Android login',
        file: 'apps/android/src/pages/login/index.vue',
        patterns: ['consumeAuthReturnPath()', 'authenticatedNavigationStarted', 'url: returnPath'],
      },
      {
        client: 'iOS request',
        file: 'apps/ios/src/api/request.ts',
        patterns: ['getToken() !== requestToken', 'stageAuthReturnPath()', 'expireSession(i18n, token)'],
      },
      {
        client: 'iOS login',
        file: 'apps/ios/src/pages/login/index.vue',
        patterns: ['consumeAuthReturnPath()', 'authenticatedNavigationStarted', 'url: returnPath'],
      },
    ],
  },
  {
    name: 'mobile market sort options',
    evidence: ['android', 'ios'].map(client => ({
      client,
      file: `apps/${client}/src/pages/market/index.vue`,
      patterns: [
        'const sorts = computed(() => commerce.directTradeEnabled',
        "{ key: 'price_asc', label: 'sortPriceUp' }",
        "{ key: 'price_desc', label: 'sortPriceDown' }",
        "if (!commerce.directTradeEnabled && sort.value !== 'default')",
      ],
    })),
  },
  {
    name: 'product inquiry login continuation and region normalization',
    evidence: [
      {
        client: 'Web detail',
        file: 'apps/web/components/product-detail.tsx',
        patterns: [
          'normalizeInquiryRegionRequirement(product.region)',
          'if (region) params.set("region", region)',
        ],
      },
      {
        client: 'Web request form',
        file: 'apps/web/components/mobile-buy-request-workspace.tsx',
        patterns: ['region: normalizeInquiryRegionRequirement(initialPrefill?.region)'],
      },
      ...['android', 'ios'].flatMap(client => [
        {
          client: `${client} detail`,
          file: `apps/${client}/src/pages/product/detail.vue`,
          patterns: [
            "source: current.market_source || current.seller_type || 'wod'",
            'region: productInquiryRegionRequirement(current.region_name, current.region_code, current.city, i18n.lang)',
            "const target = userStore.isLogin ? '/pages/buy-request/index?compose=1' : '/pages/login/index'",
            'nav(target)',
          ],
        },
        {
          client: `${client} request form`,
          file: `apps/${client}/src/pages/buy-request/index.vue`,
          patterns: ['form.region = normalizeInquiryRegionRequirement(prefill.region, i18n.lang)'],
        },
      ]),
    ],
  },
  {
    name: 'mobile rebate presentation',
    evidence: ['android', 'ios'].flatMap(client => [
      {
        client,
        file: `apps/${client}/src/pages/supplier/dashboard.vue`,
        patterns: ["t('supplierSalesRebateTitle')", "t('supplierSalesRebateCardHint'"],
      },
      {
        client,
        file: `apps/${client}/src/pages/supplier/rebate.vue`,
        patterns: [
          "t('supplierSalesRebateRuleBasis')",
          "t('supplierSalesRebateRuleTarget')",
          "t('supplierSalesRebateRuleTopUp')",
          "t('supplierSalesRebateRuleExclusions')",
          "t('supplierBuyerRebateIndependent')",
          "t('monthlyRebateCapRule'",
        ],
      },
      {
        client,
        file: `apps/${client}/src/pages/profile/index.vue`,
        patterns: [
          "t('supplierSalesRebateTitle')",
          "t('supplierSalesRebateCardHint'",
          "t('personalPurchaseRebateTitle')",
          "t('personalPurchaseRebateCardHint'",
        ],
      },
      {
        client,
        file: `apps/${client}/src/pages/rebate/index.vue`,
        patterns: [
          "t('personalPurchaseRebateRuleBasis')",
          "t('personalPurchaseRebateRuleConfirm')",
          "t('personalPurchaseRebateRulePayout')",
          "t('personalPurchaseRebateRuleExclusions')",
          "t('monthlyRebateCapRule'",
        ],
      },
    ]),
  },
  {
    name: 'mobile native video playback',
    evidence: ['android', 'ios'].flatMap(client => [
      {
        client,
        file: `apps/${client}/src/utils/community-video.ts`,
        patterns: [
          'resolveCommunityVideoStreamUrl',
          'runtime.video.createVideoPlayer',
          'COMMUNITY_VIDEO_PLAYBACK_RATES',
          'video?.playbackRate(rate)',
        ],
      },
      {
        client,
        file: `apps/${client}/src/pages/community/detail.vue`,
        patterns: [
          'requestTrustedPublicJson',
          'await openCommunityVideo',
          "uni.showLoading({ title: t('loading'), mask: true })",
        ],
      },
      {
        client,
        file: `apps/${client}/src/manifest.json`,
        patterns: ['"VideoPlayer"'],
      },
    ]),
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
  'src/pages/profile/index.vue',
  'src/pages/supplier/dashboard.vue',
  'src/pages/supplier/rebate.vue',
  'src/pages/rebate/index.vue',
  'tests/rebate-presentation.test.ts',
  'src/pages/index/index.vue',
  'src/pages/market/index.vue',
  'src/pages/product/detail.vue',
  'src/pages/community/detail.vue',
  'src/utils/community-video.ts',
  'tests/community-video-playback.test.ts',
  'src/config/home-promotions.ts',
  'src/components/HomePromoCarousel.vue',
  'src/utils/buy-request-requirements.ts',
  'src/api/revenue.ts',
  'src/pages/asset/detail.vue',
  'src/utils/asset-detail-requests.ts',
  'tests/asset-detail-resilience.test.ts',
  'src/api/request.ts',
  'tests/auth-expiry-race.test.ts',
  'src/utils/auth-return-path.ts',
  'tests/auth-return-path.test.ts',
]
for (const relative of mirroredMobileFiles) {
  const android = source(path.join('apps/android', relative)).replaceAll('\r\n', '\n')
  const ios = source(path.join('apps/ios', relative)).replaceAll('\r\n', '\n')
  if (android !== ios) violations.push(`shared mobile experience drifted: apps/android/${relative} differs from apps/ios/${relative}`)
}

// Shared Mobile code is intentionally mirrored. Keep the allowlist limited to
// package identity, build entry points, the platform constant, native manifests,
// and iOS-only App Store/privacy assets.
const allowedMobileDrift = new Set([
  'README.md',
  'package.json',
  'package-lock.json',
  'vite.config.ts',
  'src/manifest.json',
  // DCloud's native Android privacy gate runs before the WebView/JS lifecycle.
  // iOS does not consume androidPrivacy.json, so its config and regression test
  // are intentionally Android-only platform assets.
  'src/androidPrivacy.json',
  'src/utils/client-platform.ts',
  'src/static/logo/logo-1024.png',
  // iPhone application icons use Apple's 60-point @2x/@3x sizes. Android
  // consumes the shared 72/96/144/192 density icons instead.
  'src/static/logo/logo-120.png',
  'src/static/logo/logo-180.png',
  // Each manifest uses the same public identity but stores the callback scheme
  // under a platform-specific DCloud field; the matching regression assertion
  // therefore cannot be byte-for-byte identical.
  'tests/manifest-branding.test.ts',
  'tests/manifest-permissions.test.ts',
  'tests/privacy-startup.test.ts',
  // These assertions embed the platform name and therefore intentionally
  // differ by one literal while exercising the same consent contract.
  'tests/privacy-consent.test.ts',
  // iOS-only App Store privacy and native permission resources.
  'nativeResources/ios/PrivacyInfo.xcprivacy',
  'nativeResources/ios/Resources/en.lproj/InfoPlist.strings',
  'nativeResources/ios/Resources/zh-Hans.lproj/InfoPlist.strings',
  'nativeResources/ios/Resources/zh-Hant.lproj/InfoPlist.strings',
  'tests/privacy-manifest.test.ts',
])
const ignoredMobileNames = new Set(['node_modules', 'dist', '.DS_Store', '.env.local'])

function mobileFileMap(client) {
  const base = path.join(root, 'apps', client)
  const files = new Map()
  function visit(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      if (ignoredMobileNames.has(entry.name)) continue
      const absolute = path.join(directory, entry.name)
      if (entry.isDirectory()) visit(absolute)
      else if (entry.isFile()) files.set(path.relative(base, absolute).replaceAll(path.sep, '/'), absolute)
    }
  }
  visit(base)
  return files
}

const androidFiles = mobileFileMap('android')
const iosFiles = mobileFileMap('ios')
const allMobileFiles = new Set([...androidFiles.keys(), ...iosFiles.keys()])
for (const relative of [...allMobileFiles].sort()) {
  if (allowedMobileDrift.has(relative)) continue
  const androidPath = androidFiles.get(relative)
  const iosPath = iosFiles.get(relative)
  if (!androidPath || !iosPath) {
    violations.push(`shared mobile file is missing from one platform: ${relative}`)
    continue
  }
  if (!fs.readFileSync(androidPath).equals(fs.readFileSync(iosPath))) {
    violations.push(`shared mobile source drifted outside the platform allowlist: ${relative}`)
  }
}

if (violations.length) {
  console.error('Client experience parity check failed:')
  for (const violation of violations) console.error(`- ${violation}`)
  process.exit(1)
}

console.log(`Client experience parity check passed: ${commonCapabilities.length} shared capabilities cover Web, Android and iOS.`)
