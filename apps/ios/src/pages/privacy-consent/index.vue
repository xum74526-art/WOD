<template>
  <view class="page">
    <scroll-view v-if="needsConsent" scroll-y class="scroll">
      <view class="shell">
        <view class="topbar">
          <view class="brand">
            <image class="logo" src="/static/logo/logo.png" mode="aspectFit" />
            <text class="brand-name">{{ copy.appName }}</text>
          </view>
          <LanguageToggle />
        </view>

        <view class="hero">
          <text class="eyebrow">{{ copy.eyebrow }}</text>
          <text class="title">{{ copy.title }}</text>
          <text class="intro">{{ copy.intro }}</text>
          <text class="version">{{ copy.version }} {{ LEGAL_VERSION }} · {{ LEGAL_EFFECTIVE_AT }}</text>
        </view>

        <view class="card">
          <text class="section-title">{{ copy.generalTitle }}</text>
          <text class="section-copy">{{ copy.generalDescription }}</text>
          <view
            class="consent-row"
            :class="{ checked: agreementAccepted }"
            role="checkbox"
            tabindex="0"
            :aria-checked="agreementAccepted ? 'true' : 'false'"
            @tap="agreementAccepted = !agreementAccepted"
            @keydown.enter="agreementAccepted = !agreementAccepted"
            @keydown.space.prevent="agreementAccepted = !agreementAccepted"
          >
            <view class="checkbox" aria-hidden="true"><text v-if="agreementAccepted">✓</text></view>
            <view class="consent-copy">
              <text>{{ copy.generalPrefix }}</text>
              <text class="link" @tap.stop="openLegal('agreement')">{{ copy.agreement }}</text>
              <text>{{ copy.and }}</text>
              <text class="link" @tap.stop="openLegal('privacy')">{{ copy.privacy }}</text>
            </view>
          </view>
        </view>

        <view class="card">
          <text class="section-title">{{ copy.regionTitle }}</text>
          <text class="section-copy">{{ copy.regionDescription }}</text>
          <view class="region-options" role="radiogroup" :aria-label="copy.regionTitle">
            <view
              class="region-option"
              :class="{ selected: regionScope === 'mainland-china' }"
              role="radio"
              tabindex="0"
              :aria-checked="regionScope === 'mainland-china' ? 'true' : 'false'"
              @tap="selectRegion('mainland-china')"
              @keydown.enter="selectRegion('mainland-china')"
              @keydown.space.prevent="selectRegion('mainland-china')"
            >
              <view class="radio" aria-hidden="true"><view v-if="regionScope === 'mainland-china'" class="radio-dot" /></view>
              <text>{{ copy.mainland }}</text>
            </view>
            <view
              class="region-option"
              :class="{ selected: regionScope === 'other' }"
              role="radio"
              tabindex="0"
              :aria-checked="regionScope === 'other' ? 'true' : 'false'"
              @tap="selectRegion('other')"
              @keydown.enter="selectRegion('other')"
              @keydown.space.prevent="selectRegion('other')"
            >
              <view class="radio" aria-hidden="true"><view v-if="regionScope === 'other'" class="radio-dot" /></view>
              <text>{{ copy.other }}</text>
            </view>
          </view>

          <view class="cross-border-box">
            <view class="cross-border-heading">
              <text class="required-badge">{{ copy.separate }}</text>
              <text class="cross-border-title">{{ copy.crossBorderTitle }}</text>
            </view>
            <text class="cross-border-detail">{{ copy.crossBorderDetail }}</text>
            <view
              class="consent-row separate-row"
              :class="{ checked: hongKongProcessingAccepted }"
              role="checkbox"
              tabindex="0"
              :aria-checked="hongKongProcessingAccepted ? 'true' : 'false'"
              @tap="hongKongProcessingAccepted = !hongKongProcessingAccepted"
              @keydown.enter="hongKongProcessingAccepted = !hongKongProcessingAccepted"
              @keydown.space.prevent="hongKongProcessingAccepted = !hongKongProcessingAccepted"
            >
              <view class="checkbox" aria-hidden="true"><text v-if="hongKongProcessingAccepted">✓</text></view>
              <text class="consent-copy">{{ copy.crossBorderConsent }}</text>
            </view>
          </view>
          <text v-if="regionScope" class="other-note">{{ copy.regionNote }}</text>
        </view>

        <view class="actions">
          <button class="primary" :class="{ disabled: !canContinue }" :disabled="!canContinue" @tap="acceptAndContinue">
            {{ copy.accept }}
          </button>
          <button class="secondary" @tap="decline">{{ copy.decline }}</button>
        </view>
        <text class="footer-note">{{ copy.footer }}</text>
      </view>
    </scroll-view>
    <view v-else class="launch-placeholder">
      <image class="launch-logo" src="/static/logo/logo.png" mode="aspectFit" />
      <text class="brand-name">{{ copy.appName }}</text>
      <view class="launch-progress" aria-hidden="true" />
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import LanguageToggle from '@/components/LanguageToggle.vue'
import { LEGAL_EFFECTIVE_AT, LEGAL_VERSION } from '@/config/legal-documents'
import { useI18nStore } from '@/store/i18n'
import { useUserStore } from '@/store/user'
import { CLIENT_PLATFORM } from '@/utils/client-platform'
import { switchTab } from '@/utils/nav'
import { hasPendingLoginKaiCallback } from '@/utils/login-kai-callback'
import {
  acceptPrivacyConsent,
  hasCurrentPrivacyConsent,
  PRIVACY_CONSENT_EVENT,
  type PrivacyRegionScope,
} from '@/utils/privacy-consent'

const i18n = useI18nStore()
const needsConsent = ref(!hasCurrentPrivacyConsent())
const agreementAccepted = ref(false)
const hongKongProcessingAccepted = ref(false)
const regionScope = ref<PrivacyRegionScope | ''>('')
let leaving = false

const copies = {
  'zh-Hans': {
    appName: 'KAI星算', eyebrow: '隐私与数据保护', title: '请先完成隐私选择',
    intro: '在应用发起账号恢复、更新检查、第三方内容加载等业务网络请求前，请阅读并作出选择。未同意时，应用仅显示本地法律文本，不会发送业务网络请求。',
    version: '法律文本版本', generalTitle: '用户协议与隐私政策',
    generalDescription: '请完整阅读本地展示的法律文本。政策说明了处理的信息、用途、第三方、保存期限、账号注销与权利行使方式。',
    generalPrefix: '我已阅读并同意', agreement: '《用户协议》', and: '和', privacy: '《隐私政策》',
    regionTitle: '选择当前服务地区', regionDescription: '服务地区会保存在本机，用于适用规则判断；无论选择哪个地区，进入业务联网功能前都必须单独确认下方的香港存储、处理和必要传输。',
    mainland: '中国大陆', other: '其他国家或地区', separate: '单独确认', crossBorderTitle: '中国香港存储、处理与必要传输',
    crossBorderDetail: '核心 API、数据库和上传文件位于阿里云中国香港区域（cn-hongkong）。境外接收环境由锆芯期算人工智能科技（上海）有限公司运营管理，阿里云计算有限公司提供基础设施；联系方式及权利行使方式详见《隐私政策》。政策列明的账号、身份、业务、社区与客服内容，以及必要的设备、网络和日志信息，会经 HTTPS 加密传输至中国香港并在那里存储和处理，用于提供服务、履约、安全防护、故障处理和依法保存。你可通过账号功能或《隐私政策》列明的方式行使查询、更正、复制、删除、限制处理和撤回同意等权利。',
    crossBorderConsent: '我已单独阅读上述接收方、目的、方式、信息种类和权利说明，并明确同意将必要个人信息传输至中国香港存储和处理。',
    regionNote: '你的地区选择会随本次明确确认一起记录在本机；更改法律文本或同意记录版本后，应用会重新要求选择。',
    accept: '同意并进入应用', decline: '暂不同意', footer: '你可以暂不同意并关闭应用。未完成必选同意前，业务联网功能不可使用。',
    incomplete: '请完成所有必选项', declinedTitle: '尚未同意', declinedContent: '应用不会发起业务网络请求。你可以继续阅读法律文本，或关闭应用后稍后再作选择。', understood: '知道了',
  },
  'zh-Hant': {
    appName: 'KAI星算', eyebrow: '隱私與資料保護', title: '請先完成隱私選擇',
    intro: '在應用發起帳號恢復、更新檢查、第三方內容載入等業務網路請求前，請閱讀並作出選擇。未同意時，應用僅顯示本地法律文本，不會傳送業務網路請求。',
    version: '法律文本版本', generalTitle: '使用者協議與隱私政策',
    generalDescription: '請完整閱讀本地顯示的法律文本。政策說明了處理的資訊、用途、第三方、保存期限、帳號註銷與權利行使方式。',
    generalPrefix: '我已閱讀並同意', agreement: '《使用者協議》', and: '和', privacy: '《隱私政策》',
    regionTitle: '選擇目前服務地區', regionDescription: '服務地區會保存在本機，用於適用規則判斷；無論選擇哪個地區，進入業務網路功能前都必須單獨確認下方的香港儲存、處理和必要傳輸。',
    mainland: '中國大陸', other: '其他國家或地區', separate: '單獨確認', crossBorderTitle: '中國香港儲存、處理與必要傳輸',
    crossBorderDetail: '核心 API、資料庫和上傳檔案位於阿里雲中國香港區域（cn-hongkong）。境外接收環境由锆芯期算人工智能科技（上海）有限公司運營管理，阿里雲計算有限公司提供基礎設施；聯絡方式及權利行使方式詳見《隱私政策》。政策列明的帳號、身份、業務、社區與客服內容，以及必要的裝置、網路和日誌資訊，會經 HTTPS 加密傳輸至中國香港並在當地儲存和處理，用於提供服務、履約、安全防護、故障處理和依法保存。你可透過帳號功能或《隱私政策》列明的方式行使查詢、更正、複製、刪除、限制處理和撤回同意等權利。',
    crossBorderConsent: '我已單獨閱讀上述接收方、目的、方式、資訊種類和權利說明，並明確同意將必要個人資訊傳輸至中國香港儲存和處理。',
    regionNote: '你的地區選擇會隨本次明確確認一起記錄在本機；更改法律文本或同意記錄版本後，應用會重新要求選擇。',
    accept: '同意並進入應用', decline: '暫不同意', footer: '你可以暫不同意並關閉應用。未完成必選同意前，業務網路功能不可使用。',
    incomplete: '請完成所有必選項', declinedTitle: '尚未同意', declinedContent: '應用不會發起業務網路請求。你可以繼續閱讀法律文本，或關閉應用後稍後再作選擇。', understood: '知道了',
  },
  en: {
    appName: 'KAI Star', eyebrow: 'Privacy and data protection', title: 'Make your privacy choices first',
    intro: 'Before the app sends service network requests for account recovery, update checks, or third-party content loading, please read and make your choices. Until then, the app displays only bundled legal text and sends no service network request.',
    version: 'Legal text version', generalTitle: 'User Agreement and Privacy Policy',
    generalDescription: 'Read the bundled legal text in full. It explains the data processed, purposes, third parties, retention, account deletion, and how to exercise your rights.',
    generalPrefix: 'I have read and agree to the ', agreement: 'User Agreement', and: ' and ', privacy: 'Privacy Policy',
    regionTitle: 'Select your current service region', regionDescription: 'Your service region is stored on this device to determine applicable rules. Whichever region you select, you must separately confirm the Hong Kong storage, processing, and necessary transfer below before using service network features.',
    mainland: 'Mainland China', other: 'Another country or region', separate: 'Separate confirmation', crossBorderTitle: 'Hong Kong storage, processing, and necessary transfer',
    crossBorderDetail: 'The core API, database, and uploads are hosted in Alibaba Cloud Hong Kong (cn-hongkong). The overseas receiving environment is operated and managed by Zircon Core Futures Computing Artificial Intelligence Technology (Shanghai) Co., Ltd., with Alibaba Cloud Computing Co., Ltd. providing infrastructure; contact and rights-request methods are listed in the Privacy Policy. Account, identity, business, community and support content, plus necessary device, network and log data, is encrypted by HTTPS in transit to Hong Kong SAR and processed there for service, fulfilment, security, troubleshooting and required retention. Exercise access, correction, copy, deletion, restriction and withdrawal rights through account features or the methods listed in the Privacy Policy.',
    crossBorderConsent: 'I have separately read the recipient, purpose, method, data categories, and rights notice above, and explicitly consent to the transfer of necessary personal information to Hong Kong SAR for storage and processing.',
    regionNote: 'Your region choice is stored on this device together with this explicit confirmation. The app will ask again after the legal text or consent-record version changes.',
    accept: 'Accept and enter the app', decline: 'Not now', footer: 'You may decline and close the app. Service network features remain unavailable until all required choices are complete.',
    incomplete: 'Complete all required choices', declinedTitle: 'Consent not given', declinedContent: 'The app will not send service network requests. You can continue reading the legal text or close the app and decide later.', understood: 'OK',
  },
} as const

const copy = computed(() => copies[i18n.lang])
const canContinue = computed(() => agreementAccepted.value
  && regionScope.value !== ''
  && hongKongProcessingAccepted.value)

function selectRegion(value: PrivacyRegionScope) {
  regionScope.value = value
}

function openLegal(type: 'agreement' | 'privacy') {
  uni.navigateTo({ url: `/pages/agreement/index?type=${type}&from=privacy-consent` })
}

async function enterApp() {
  if (leaving) return
  leaving = true
  const user = useUserStore()
  if (!user.token || hasPendingLoginKaiCallback()) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }
  await user.restore()
  if (!hasCurrentPrivacyConsent()) {
    leaving = false
    needsConsent.value = true
    return
  }
  // An OAuth/password-reset callback may already have routed elsewhere while
  // the saved session was being restored. Do not overwrite that destination.
  const pages = getCurrentPages()
  const route = pages[pages.length - 1]?.route
  if (route && route !== 'pages/privacy-consent/index') return
  if (!user.isLogin) {
    uni.reLaunch({ url: '/pages/login/index' })
    return
  }
  switchTab('/pages/index/index', { fallbackToReLaunch: true })
}

function acceptAndContinue() {
  if (!canContinue.value || !regionScope.value) {
    uni.showToast({ title: copy.value.incomplete, icon: 'none' })
    return
  }
  try {
    acceptPrivacyConsent({
      language: i18n.lang,
      platform: CLIENT_PLATFORM,
      regionScope: regionScope.value,
      agreementAndPrivacyAccepted: agreementAccepted.value,
      hongKongProcessingAccepted: hongKongProcessingAccepted.value,
    })
  } catch {
    uni.showToast({ title: copy.value.incomplete, icon: 'none' })
    return
  }
  uni.$emit(PRIVACY_CONSENT_EVENT)
  needsConsent.value = false
  enterApp()
}

function decline() {
  uni.showModal({
    title: copy.value.declinedTitle,
    content: copy.value.declinedContent,
    showCancel: false,
    confirmText: copy.value.understood,
  })
}

onLoad(() => {
  if (hasCurrentPrivacyConsent()) setTimeout(enterApp, 0)
})
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); color: var(--text); }
.launch-placeholder { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 24rpx; }
.launch-logo { width: 100rpx; height: 100rpx; border-radius: 24rpx; }
.launch-progress { width: 32rpx; height: 32rpx; border: 3rpx solid var(--border); border-top-color: var(--primary); border-radius: 50%; animation: launch-spin 900ms linear infinite; }
@keyframes launch-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .launch-progress { animation: none; } }
.scroll { height: 100vh; }
.shell { box-sizing: border-box; min-height: 100vh; padding: calc(24rpx + var(--safe-top)) 30rpx calc(44rpx + var(--safe-bottom)); }
.topbar, .brand, .consent-row, .region-option, .cross-border-heading { display: flex; align-items: center; }
.topbar { justify-content: space-between; gap: 20rpx; }
.brand { gap: 14rpx; }
.logo { width: 62rpx; height: 62rpx; border-radius: 16rpx; }
.brand-name { color: var(--text); font-size: 28rpx; font-weight: 800; }
.hero { padding: 64rpx 6rpx 34rpx; }
.eyebrow { display: block; color: var(--primary); font-size: 22rpx; font-weight: 800; letter-spacing: 2rpx; text-transform: uppercase; }
.title { display: block; margin-top: 13rpx; color: var(--text); font-size: 48rpx; font-weight: 850; line-height: 1.25; }
.intro { display: block; margin-top: 20rpx; color: var(--text-sub); font-size: 25rpx; line-height: 1.72; }
.version { display: block; margin-top: 18rpx; color: var(--text-dim); font-size: 20rpx; }
.card { margin-top: 22rpx; padding: 28rpx; border: 1rpx solid var(--card-border); border-radius: 24rpx; background: var(--card); box-shadow: var(--shadow); }
.section-title { display: block; color: var(--text); font-size: 29rpx; font-weight: 800; }
.section-copy { display: block; margin-top: 12rpx; color: var(--text-sub); font-size: 23rpx; line-height: 1.65; }
.consent-row { gap: 18rpx; margin-top: 24rpx; padding: 22rpx; border: 1rpx solid var(--border); border-radius: 18rpx; background: var(--bg); }
.consent-row.checked { border-color: var(--primary); background: var(--primary-soft); }
.checkbox { flex: 0 0 auto; width: 38rpx; height: 38rpx; border: 2rpx solid var(--text-dim); border-radius: 10rpx; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 25rpx; font-weight: 800; }
.checked .checkbox { border-color: var(--primary); background: var(--primary); }
.consent-copy { flex: 1; color: var(--text-sub); font-size: 23rpx; line-height: 1.65; }
.link { color: var(--primary); font-weight: 750; }
.region-options { display: flex; gap: 16rpx; margin-top: 22rpx; }
.region-option { flex: 1; gap: 12rpx; min-height: 76rpx; padding: 0 20rpx; border: 1rpx solid var(--border); border-radius: 16rpx; background: var(--bg); color: var(--text-sub); font-size: 23rpx; }
.region-option.selected { border-color: var(--primary); color: var(--text); background: var(--primary-soft); font-weight: 700; }
.radio { width: 30rpx; height: 30rpx; border: 2rpx solid var(--text-dim); border-radius: 50%; display: flex; align-items: center; justify-content: center; }
.selected .radio { border-color: var(--primary); }
.radio-dot { width: 16rpx; height: 16rpx; border-radius: 50%; background: var(--primary); }
.cross-border-box { margin-top: 24rpx; padding: 24rpx; border: 1rpx solid rgba(24, 175, 196, 0.28); border-radius: 18rpx; background: var(--primary-soft); }
.cross-border-heading { flex-wrap: wrap; gap: 12rpx; }
.required-badge { padding: 5rpx 12rpx; border-radius: 999rpx; background: var(--primary); color: #fff; font-size: 19rpx; font-weight: 800; }
.cross-border-title { color: var(--text); font-size: 25rpx; font-weight: 800; }
.cross-border-detail { display: block; margin-top: 16rpx; color: var(--text-sub); font-size: 22rpx; line-height: 1.7; }
.separate-row { background: var(--bg); }
.other-note { display: block; margin-top: 22rpx; color: var(--text-sub); font-size: 22rpx; line-height: 1.6; }
.actions { margin-top: 30rpx; }
.primary, .secondary { width: 100%; height: 92rpx; border-radius: 20rpx; font-size: 27rpx; font-weight: 800; }
.primary { display: flex; align-items: center; justify-content: center; background: var(--primary); color: #fff; }
.primary.disabled { opacity: 0.42; }
.secondary { margin-top: 14rpx; color: var(--text-sub); }
.footer-note { display: block; padding: 18rpx 12rpx 0; color: var(--text-dim); font-size: 20rpx; line-height: 1.55; text-align: center; }
</style>
