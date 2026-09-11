<template>
  <view class="page">
    <AppNavBar :title="t(showForm ? 'postBuyRequest' : viewMode === 'seller' ? 'requestMarket' : 'myBuyRequests')" />
    <view class="shell">
      <template v-if="!showForm">
        <view v-if="sellerViewAvailable" class="view-switch">
          <SegmentedControl :items="viewTabs" :model-value="viewTab" @update:model-value="setViewTab" />
        </view>

        <view v-if="viewMode === 'buyer'" class="summary-strip">
          <view class="summary-item">
            <text class="summary-value">{{ summary.active }}</text>
            <text class="summary-label">{{ t('activeRequests') }}</text>
          </view>
          <view class="summary-item">
            <text class="summary-value primary">{{ summary.new_quotes }}</text>
            <text class="summary-label">{{ t('newQuotes') }}</text>
          </view>
          <view class="summary-item">
            <text class="summary-value">{{ summary.pending_confirmation }}</text>
            <text class="summary-label">{{ t('pendingConfirmation') }}</text>
          </view>
        </view>

        <SegmentedControl :items="requestTabs" :model-value="requestTab" @update:model-value="setRequestTab" />

        <view v-if="loading" class="list-skeleton">
          <view v-for="item in 3" :key="item" class="sk-card"></view>
        </view>
        <view v-else-if="loadError" class="empty-card">
          <AppIcon name="order" :size="52" />
          <text class="empty-title">{{ t('dataUnavailable') }}</text>
          <view class="empty-action" @tap="load">{{ t('retry') }}</view>
        </view>
        <view v-else-if="!requests.length" class="empty-card">
          <AppIcon name="order" :size="52" />
          <text class="empty-title">{{ t(viewMode === 'seller' ? 'noAvailableRequests' : 'noBuyRequests') }}</text>
          <text class="empty-copy">{{ t(viewMode === 'seller' ? 'sellerAvailableRequestHint' : requestType === 'online' ? 'onlineRequestHint' : 'offlineRequestHint') }}</text>
          <view v-if="viewMode === 'buyer'" class="empty-action" @tap="openForm">{{ t('postBuyRequest') }}</view>
        </view>

        <view v-for="item in requests" :key="item.id" class="request-card" :class="{ 'own-request': viewMode === 'seller' && isOwnRequest(item) }" @tap="openDetail(item)">
          <view class="request-head">
            <view class="type-label" :class="item.request_type">{{ t(item.request_type === 'online' ? 'onlineRequest' : 'offlineRequest') }}</view>
            <view class="request-flags">
              <text v-if="viewMode === 'seller' && isOwnRequest(item)" class="own-request-badge">{{ t('ownRequestBadge') }}</text>
              <text class="status-label" :class="item.status">{{ statusLabel(item.status) }}</text>
            </view>
          </view>
          <text class="request-model">{{ item.gpu_model }}<text v-if="item.gpu_variant"> {{ item.gpu_variant }}</text></text>
          <view class="request-specs">
            <text>{{ t('gpuQuantityValue', { count: item.quantity }) }}</text>
            <text v-if="item.gpu_hours">{{ t('gpuHoursValue', { count: item.gpu_hours }) }}</text>
          <text v-if="item.region">{{ localizeRegionName(item.region, i18n.lang) }}</text>
          </view>
          <view class="request-bottom">
            <view>
              <text class="budget-label">{{ t('requestProgress') }}</text>
              <text class="budget-value">{{ statusLabel(item.status) }}</text>
            </view>
            <view v-if="viewMode === 'buyer'" class="quote-box">
              <text class="quote-value">{{ item.quote_count }}</text>
              <text class="quote-label">{{ t('quotesReceived') }}</text>
            </view>
          </view>
          <text class="expiry">{{ expiryText(item.expires_at) }}</text>
        </view>

        <view v-if="viewMode === 'buyer' && requests.length" class="post-button" @tap="openForm">
          <text class="plus">＋</text><text>{{ t('postBuyRequest') }}</text>
        </view>
      </template>

      <template v-else>
        <view class="mode-intro">
          <text class="mode-title">{{ t(requestType === 'online' ? 'onlineRequest' : 'offlineRequest') }}</text>
          <text class="mode-copy">{{ t(requestType === 'online' ? 'onlineRequestFormHint' : 'offlineRequestFormHint') }}</text>
        </view>

        <view v-if="inquiryContext" class="inquiry-context">
          <view>
            <text class="context-label">{{ t('inquiryResource') }}</text>
            <text class="context-title">{{ inquiryContext.product_name || inquiryContext.gpu_model }}</text>
            <text class="context-meta">{{ inquiryContext.gpu_model }} {{ inquiryContext.gpu_variant || '' }}</text>
          </view>
          <view class="context-provider">
            <text>{{ t('inquirySeller') }}</text>
            <text>{{ inquiryContext.seller_name || t('verifiedMerchant') }}</text>
          </view>
        </view>

        <view class="form-section">
          <view class="field">
            <text class="field-label">{{ t('gpuModel') }}</text>
            <view v-if="inquiryContext" class="picker-value readonly-value">{{ form.gpu_model }} {{ form.gpu_variant }}</view>
            <picker v-else-if="marketModels.length" :range="modelLabels" :value="modelIndex" @change="onModelChange">
              <view class="picker-value">{{ modelLabels[modelIndex] || t('selectGpuModel') }}<text class="picker-arrow">⌄</text></view>
            </picker>
            <input v-else v-model="form.gpu_model" class="field-input" :placeholder="t('enterGpuModel')" placeholder-class="placeholder" />
          </view>
          <view class="field two-col">
            <view class="half">
              <text class="field-label">{{ t('quantity') }}</text>
              <input v-model="form.quantity" type="number" class="field-input" :placeholder="t('enterQuantity')" placeholder-class="placeholder" />
            </view>
            <view v-if="requestType === 'online'" class="half">
              <text class="field-label">{{ t('totalGpuHours') }}</text>
              <input v-model="form.gpu_hours" type="number" class="field-input" :placeholder="t('enterGpuHours')" placeholder-class="placeholder" />
            </view>
          </view>
          <view class="field">
            <text class="field-label">{{ t('regionRequirement') }}</text>
            <input v-model="form.region" class="field-input" :placeholder="t('regionOptional')" placeholder-class="placeholder" />
          </view>

          <template v-if="requestType === 'online'">
            <view class="field two-col">
              <view class="half">
                <text class="field-label">{{ t('billingMode') }}</text>
                <picker :range="billingLabels" :value="billingIndex" @change="billingIndex = Number($event.detail.value)">
                  <view class="picker-value">{{ billingLabels[billingIndex] }}<text class="picker-arrow">⌄</text></view>
                </picker>
              </view>
              <view class="half">
                <text class="field-label">{{ t('requestExpiration') }}</text>
                <picker :range="expiryLabels" :value="expiryIndex" @change="expiryIndex = Number($event.detail.value)">
                  <view class="picker-value">{{ expiryLabels[expiryIndex] }}<text class="picker-arrow">⌄</text></view>
                </picker>
              </view>
            </view>
          </template>

          <template v-else>
            <view class="option-row">
              <view><text class="option-title">{{ t('needHosting') }}</text><text class="option-copy">{{ t('hostingOptionHint') }}</text></view>
              <switch :checked="form.need_hosting" color="#18AFC4" @change="onNeedHostingChange" />
            </view>
            <view class="option-row">
              <view><text class="option-title">{{ t('invoiceRequired') }}</text><text class="option-copy">{{ t('invoiceOptionHint') }}</text></view>
              <switch :checked="form.invoice_required" color="#18AFC4" @change="onInvoiceChange" />
            </view>
          </template>

          <view class="field two-col">
            <view class="half">
              <text class="field-label">{{ t('contactName') }}</text>
              <input v-model="form.contact" class="field-input" :placeholder="t('enterContactName')" placeholder-class="placeholder" />
            </view>
            <view class="half">
              <text class="field-label">{{ t('contactPhone') }}</text>
              <input v-model="form.phone" type="tel" maxlength="32" class="field-input" :placeholder="t('enterContactPhone')" placeholder-class="placeholder" />
            </view>
          </view>

          <view class="field">
            <text class="field-label">{{ t('additionalRequirements') }}</text>
            <textarea v-model="form.remark" class="field-textarea" :placeholder="t('requirementsPlaceholder')" placeholder-class="placeholder" maxlength="500" />
          </view>
        </view>

        <view class="form-actions">
          <view class="cancel-button" @tap="closeForm">{{ t('cancel') }}</view>
          <view class="submit-button" :class="{ disabled: submitting || !commerce.matchmakingEnabled }" @tap="submitRequest">{{ t(submitting ? 'submitting' : 'submitRequirement') }}</view>
        </view>
      </template>
    </view>

    <view v-if="detailLoading" class="sheet-mask loading-mask">
      <view class="detail-loading"><view class="loading-spinner"></view><text>{{ t('loadingRequestDetail') }}</text></view>
    </view>

    <view v-if="detail" class="sheet-mask" @tap="closeDetail">
      <view class="detail-sheet" @tap.stop>
        <view class="sheet-handle"></view>
        <view class="sheet-head">
          <view>
            <text class="sheet-eyebrow">{{ t(viewMode === 'seller' ? 'anonymousRequestId' : 'requestId', { id: detail.request.id }) }}</text>
            <text class="sheet-title">{{ detail.request.gpu_model }} {{ detail.request.gpu_variant }}</text>
            <text class="sheet-sub">{{ statusLabel(detail.deal?.status || detail.request.status) }}</text>
          </view>
          <text class="sheet-close" @tap="closeDetail">×</text>
        </view>
        <scroll-view scroll-y class="sheet-scroll">
          <view class="detail-grid">
            <view class="detail-cell"><text class="detail-label">{{ t('quantity') }}</text><text class="detail-value">{{ detail.request.quantity }}</text></view>
            <view v-if="detail.request.gpu_hours" class="detail-cell"><text class="detail-label">{{ t('totalGpuHours') }}</text><text class="detail-value">{{ detail.request.gpu_hours }}</text></view>
          <view class="detail-cell"><text class="detail-label">{{ t('region') }}</text><text class="detail-value">{{ detail.request.region ? localizeRegionName(detail.request.region, i18n.lang) : t('notLimited') }}</text></view>
            <view v-if="viewMode === 'buyer'" class="detail-cell"><text class="detail-label">{{ t('quotesReceived') }}</text><text class="detail-value">{{ detail.request.quote_count }}</text></view>
          </view>
          <text v-if="detail.request.requirements?.remark" class="detail-remark">{{ detail.request.requirements.remark }}</text>

          <template v-if="viewMode === 'buyer'">
            <text class="section-title">{{ t('receivedQuotes') }}</text>
            <view v-if="!detail.quotes.length" class="quote-empty">{{ t('noQuotesYet') }}</view>
            <view v-for="quote in detail.quotes" :key="quote.id" class="quote-card">
              <view class="quote-main">
                <view>
                  <text class="quote-supplier">{{ quote.supplier_name }}</text>
                  <text class="revision-meta">{{ t('quoteRevision', { count: quoteRevisionCount(quote) }) }}</text>
                </view>
                <text class="quote-price">{{ quoteAmount(quote) }}</text>
              </view>
              <view class="quote-meta-grid">
                <view><text>{{ t('deliveryTime') }}</text><text>{{ quoteDeliveryText(quote) }}</text></view>
                <view><text>{{ t('planValidity') }}</text><text>{{ expiryText(latestQuoteRevision(quote).expires_at || quote.expires_at) }}</text></view>
              </view>
              <text class="quote-message">{{ latestQuoteRevision(quote).message || quote.message || t('noAdditionalMessage') }}</text>
              <text class="quote-status">{{ statusLabel(quote.status) }}</text>
              <view class="quote-actions">
                <view v-if="canBuyerCounter(quote)" class="secondary-action" @tap.stop="beginQuoteEdit(quote, 'buyer')">{{ t('counterProposal') }}</view>
                <view v-if="canSelectQuote(quote)" class="primary-action" :class="{ disabled: selectingQuoteId === quote.id || actionBusy }" @tap.stop="confirmQuoteSelection(quote)">
                  {{ t(commerce.matchmakingEnabled ? 'selectSolutionAndCoordinate' : 'selectQuote') }}
                </view>
              </view>
              <view v-if="editingQuoteId === quote.id && quoteFormRole === 'buyer'" class="inline-form">
                <text class="inline-form-title">{{ t('submitCounterProposal') }}</text>
                <MatchmakingQuoteForm v-model="quoteForm" :submit-label="t('submitCounterProposal')" :busy="actionBusy" @submit="submitQuoteForm" @cancel="cancelQuoteEdit" />
              </view>
            </view>
          </template>
          <template v-else>
            <view v-if="isOwnRequest(detail.request)" class="seller-detail-note">{{ t('ownRequestReadOnlyHint') }}</view>
            <template v-else>
              <view class="privacy-note"><text>{{ t('buyerPrivacyProtected') }}</text><text>{{ t('buyerPrivacyProtectedHint') }}</text></view>
              <text class="section-title">{{ t('myProposal') }}</text>
              <view v-if="sellerQuote" class="quote-card seller-quote-card">
                <view class="quote-main">
                  <view><text class="quote-supplier">{{ t('submittedProposal') }}</text><text class="revision-meta">{{ t('quoteRevision', { count: quoteRevisionCount(sellerQuote) }) }}</text></view>
                  <text class="quote-price">{{ quoteAmount(sellerQuote) }}</text>
                </view>
                <view class="quote-meta-grid">
                  <view><text>{{ t('deliveryTime') }}</text><text>{{ quoteDeliveryText(sellerQuote) }}</text></view>
                  <view><text>{{ t('planValidity') }}</text><text>{{ expiryText(latestQuoteRevision(sellerQuote).expires_at || sellerQuote.expires_at) }}</text></view>
                </view>
                <text class="quote-message">{{ latestQuoteRevision(sellerQuote).message || sellerQuote.message || t('noAdditionalMessage') }}</text>
                <view class="quote-actions">
                  <view v-if="canSellerRevise" class="secondary-action" @tap.stop="beginQuoteEdit(sellerQuote, 'seller')">{{ t('reviseProposal') }}</view>
                  <view v-if="canSellerWithdraw" class="danger-action" :class="{ disabled: actionBusy }" @tap.stop="confirmWithdrawQuote(sellerQuote)">{{ t('withdrawProposal') }}</view>
                </view>
              </view>
              <view v-if="canSellerSubmit || (editingQuoteId === sellerQuote?.id && quoteFormRole === 'seller')" class="action-panel">
                <text class="inline-form-title">{{ t(canSellerSubmit ? 'submitProposal' : 'reviseProposal') }}</text>
                <MatchmakingQuoteForm v-model="quoteForm" :submit-label="t(canSellerSubmit ? 'submitProposal' : 'saveProposalRevision')" :busy="actionBusy" :show-cancel="!canSellerSubmit" @submit="submitQuoteForm" @cancel="cancelQuoteEdit" />
              </view>
              <view v-else-if="!sellerQuote && !detail.deal" class="seller-detail-note">{{ t('proposalUnavailableHint') }}</view>
            </template>
          </template>

          <view v-if="detail.deal" class="deal-section">
            <view class="deal-head"><view><text class="section-kicker">{{ t('platformCoordination') }}</text><text class="section-title compact">{{ statusLabel(detail.deal.status) }}</text></view><text class="deal-id">#{{ detail.deal.id }}</text></view>
            <view class="timeline">
              <view v-for="(event, index) in timelineItems" :key="event.key" class="timeline-item" :class="event.state">
                <view class="timeline-rail"><view class="timeline-dot"></view><view v-if="index < timelineItems.length - 1" class="timeline-line"></view></view>
                <view class="timeline-copy"><text>{{ event.label }}</text><text v-if="event.meta">{{ event.meta }}</text></view>
              </view>
            </view>

            <view v-if="viewMode === 'seller' && (canSupplierConfirm || canSupplierDecline)" class="action-panel compact-panel">
              <text class="inline-form-title">{{ t('supplierResourceConfirmation') }}</text>
              <text class="form-hint">{{ t('supplierResourceConfirmationHint') }}</text>
              <view class="quote-actions">
                <view v-if="canSupplierDecline" class="danger-action" :class="{ disabled: actionBusy }" @tap="confirmSupplierDecision(false)">{{ t('cannotProvideResource') }}</view>
                <view v-if="canSupplierConfirm" class="primary-action" :class="{ disabled: actionBusy }" @tap="confirmSupplierDecision(true)">{{ t('confirmResourceAvailable') }}</view>
              </view>
            </view>

            <view v-if="viewMode === 'seller' && canSubmitCredential" class="action-panel credential-form">
              <text class="inline-form-title">{{ t('credentialEscrow') }}</text>
              <text class="form-hint">{{ t('credentialEscrowHint') }}</text>
              <view class="field two-col">
                <view class="half"><text class="field-label">{{ t('sshHost') }}</text><input v-model="credentialForm.host" class="field-input" :placeholder="t('sshHostPlaceholder')" /></view>
                <view class="half"><text class="field-label">{{ t('sshPort') }}</text><input v-model="credentialForm.port" type="number" class="field-input" placeholder="22" /></view>
              </view>
              <view class="field"><text class="field-label">{{ t('sshUsername') }}</text><input v-model="credentialForm.username" class="field-input" :placeholder="t('sshUsernamePlaceholder')" /></view>
              <view class="field"><text class="field-label">{{ t('credentialType') }}</text><picker :range="credentialTypeLabels" :value="credentialTypeIndex" @change="credentialTypeIndex = Number($event.detail.value)"><view class="picker-value">{{ credentialTypeLabels[credentialTypeIndex] }}<text class="picker-arrow">⌄</text></view></picker></view>
              <view class="field">
                <text class="field-label">{{ t(credentialTypeIndex === 0 ? 'sshPassword' : 'sshPrivateKey') }}</text>
                <input v-if="credentialTypeIndex === 0" v-model="credentialForm.secret" type="password" class="field-input" :placeholder="t('sshPasswordPlaceholder')" />
                <textarea v-else v-model="credentialForm.secret" class="field-textarea short" :placeholder="t('sshPrivateKeyPlaceholder')" />
              </view>
              <view class="field"><text class="field-label">{{ t('credentialNote') }}</text><textarea v-model="credentialForm.note" class="field-textarea short" :placeholder="t('credentialNotePlaceholder')" /></view>
              <view class="primary-action full" :class="{ disabled: actionBusy || !credentialFormValid }" @tap="submitCredential">{{ t('submitCredentialToPlatform') }}</view>
            </view>

            <view v-if="viewMode === 'buyer' && credentialLoading" class="credential-card muted">{{ t('loadingCredential') }}</view>
            <view v-else-if="viewMode === 'buyer' && releasedCredential" class="credential-card">
              <view class="credential-head"><view><text class="section-kicker">{{ t('credentialEscrow') }}</text><text class="credential-title">{{ releasedCredential.username }}@{{ releasedCredential.host }}:{{ releasedCredential.port }}</text></view><view class="secondary-action small" @tap="copyCredential">{{ t('copyCredential') }}</view></view>
              <view class="credential-secret"><text>{{ t(releasedCredential.auth_type === 'password' ? 'sshPassword' : 'sshPrivateKey') }}</text><text selectable>{{ releasedCredential.secret || t('credentialUnavailable') }}</text></view>
              <text v-if="releasedCredential.note" class="credential-note">{{ releasedCredential.note }}</text>
              <view class="quote-actions">
                <view v-if="canReportDelivery" class="danger-action" :class="{ disabled: actionBusy }" @tap="openIssueForm">{{ t('reportConnectionIssue') }}</view>
                <view v-if="canConfirmDelivery" class="primary-action" :class="{ disabled: actionBusy }" @tap="confirmCredentialUsable">{{ t('confirmConnectionUsable') }}</view>
              </view>
              <view v-if="showIssueForm" class="inline-form">
                <text class="field-label">{{ t('issueReason') }}</text>
                <textarea v-model="issueReason" class="field-textarea short" :placeholder="t('issueReasonPlaceholder')" maxlength="500" />
                <view class="primary-action full" :class="{ disabled: actionBusy || !issueReason.trim() }" @tap="reportCredentialIssue">{{ t('submitIssue') }}</view>
              </view>
            </view>
            <view v-else-if="viewMode === 'buyer' && canViewCredential && credentialError" class="credential-card muted"><text>{{ t('credentialLoadFailed') }}</text><view class="secondary-action small" @tap="loadReleasedCredential">{{ t('retry') }}</view></view>
          </view>
        </scroll-view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import {
  confirmBuyRequestDealBySupplier,
  confirmBuyRequestDelivery,
  counterBuyRequestQuote,
  createBuyRequest,
  declineBuyRequestDealBySupplier,
  getBuyRequestDetail,
  getBuyRequestCredential,
  getBuyRequests,
  getBuyRequestSummary,
  reportBuyRequestDelivery,
  selectBuyRequestQuote,
  submitBuyRequestCredential,
  submitBuyRequestQuote,
  withdrawBuyRequestQuote,
  type BuyRequestCredential,
  type BuyRequestDetail,
  type BuyRequestItem,
  type BuyRequestQuote,
  type BuyRequestPayload,
  type BuyRequestQuotePayload,
  type BuyRequestQuoteRevision,
  type BuyRequestView,
} from '@/api/buy-request'
import { getMarketModels, type MarketModel } from '@/api/market'
import AppNavBar from '@/components/AppNavBar.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import AppIcon from '@/components/AppIcon.vue'
import MatchmakingQuoteForm, { type MatchmakingQuoteFormValue } from '@/components/MatchmakingQuoteForm.vue'
import { useI18nStore } from '@/store/i18n'
import { useUserStore } from '@/store/user'
import { useCommerceStore } from '@/store/commerce'
import { localizeRegionName } from '@/utils/region-name'
import { formatQuoteAmount } from '@/utils/quote-currency'
import { ensureClientRequestIntent, type ClientRequestIntent } from '@/utils/client-request-intent'
import { normalizeBuyRequestContactPhone } from '@/utils/buy-request-contact'
import {
  canBuyerConfirmDelivery as buyerCanConfirmDelivery,
  canBuyerReportDelivery as buyerCanReportDelivery,
  canBuyerSelectQuote,
  canBuyerViewCredential as buyerCanViewCredential,
  canCounterQuote,
  canSellerSubmitQuote,
  canSupplierConfirmDeal,
  canSupplierDeclineDeal,
  canSupplierSubmitCredential,
  canWithdrawQuote,
} from '@/utils/matchmaking-actions'
import {
  clearInquiryRequestPrefill,
  readInquiryRequestPrefill,
  type InquiryRequestPrefill,
} from '@/utils/inquiry-request'

const i18n = useI18nStore()
const { t } = i18n
const userStore = useUserStore()
const commerce = useCommerceStore()
const requestTab = ref(0)
const viewMode = ref<BuyRequestView>('buyer')
const requestedInitialView = ref<BuyRequestView>('buyer')
const viewInitialized = ref(false)
const requests = ref<BuyRequestItem[]>([])
const summary = reactive({ active: 0, new_quotes: 0, pending_confirmation: 0 })
const loading = ref(false)
const loadError = ref(false)
const showForm = ref(false)
const submitting = ref(false)
const pendingRequestIntent = ref<ClientRequestIntent | null>(null)
const selectingQuoteId = ref<number | null>(null)
const actionBusy = ref(false)
const detailLoading = ref(false)
const editingQuoteId = ref<number | null>(null)
const quoteFormRole = ref<'buyer' | 'seller'>('seller')
const quoteForm = ref<MatchmakingQuoteFormValue>(emptyQuoteForm())
const releasedCredential = ref<BuyRequestCredential | null>(null)
const credentialLoading = ref(false)
const credentialError = ref(false)
const showIssueForm = ref(false)
const issueReason = ref('')
const credentialTypeIndex = ref(0)
const credentialForm = reactive({ host: '', port: '22', username: '', secret: '', note: '' })
const marketModels = ref<MarketModel[]>([])
const modelIndex = ref(0)
const billingIndex = ref(0)
const expiryIndex = ref(2)
const inquiryContext = ref<InquiryRequestPrefill | null>(null)
const composeRequested = ref(false)
const detail = ref<BuyRequestDetail | null>(null)
const form = reactive({
  gpu_model: '', gpu_variant: '', quantity: '1', gpu_hours: '', region: '', contact: '', phone: '', remark: '', need_hosting: false, invoice_required: false,
})

const requestType = computed<'online' | 'offline'>(() => requestTab.value === 0 ? 'online' : 'offline')
const requestTabs = computed(() => [t('onlineRequest'), t('offlineRequest')])
const sellerViewAvailable = computed(() => userStore.userInfo?.supplier_status === 'approved')
const viewTabs = computed(() => [t('availableRequests'), t('myBuyRequests')])
const viewTab = computed(() => viewMode.value === 'seller' ? 0 : 1)
const modelLabels = computed(() => marketModels.value.map((item) => `${item.gpu_model}${item.gpu_variant ? ` ${item.gpu_variant}` : ''}`))
const billingLabels = computed(() => [t('onDemand'), t('interruptible'), t('reserved')])
const billingValues = ['ondemand', 'bid', 'reserved']
const expiryLabels = computed(() => [t('oneHour'), t('sixHours'), t('twentyFourHours'), t('threeDays')])
const expiryValues = [1, 6, 24, 72]
const credentialTypeLabels = computed(() => [t('credentialPassword'), t('credentialPrivateKey')])
const sellerQuote = computed(() => {
  if (!detail.value || viewMode.value !== 'seller') return null
  if (detail.value.deal) {
    const selected = detail.value.quotes.find(item => item.id === detail.value?.deal?.quote_id)
    if (selected) return selected
  }
  return detail.value.quotes[0] || null
})
const canSellerSubmit = computed(() => Boolean(detail.value && canSellerSubmitQuote({
  matchmakingEnabled: commerce.matchmakingEnabled,
  isOwnRequest: isOwnRequest(detail.value.request),
  requestStatus: detail.value.request.status,
  ownQuote: sellerQuote.value && ['active', 'countered', 'revised'].includes(sellerQuote.value.status) ? sellerQuote.value : null,
})))
const canSellerRevise = computed(() => Boolean(detail.value && sellerQuote.value && canCounterQuote({
  matchmakingEnabled: commerce.matchmakingEnabled,
  role: 'seller',
  isOwnRequest: isOwnRequest(detail.value.request),
  requestStatus: detail.value.request.status,
  quote: sellerQuote.value,
  deal: detail.value.deal,
})))
const canSellerWithdraw = computed(() => Boolean(detail.value && sellerQuote.value && canWithdrawQuote({
  matchmakingEnabled: commerce.matchmakingEnabled,
  isOwnRequest: isOwnRequest(detail.value.request),
  requestStatus: detail.value.request.status,
  quote: sellerQuote.value,
  deal: detail.value.deal,
})))
const canSupplierConfirm = computed(() => viewMode.value === 'seller' && canSupplierConfirmDeal(detail.value?.deal))
const canSupplierDecline = computed(() => viewMode.value === 'seller' && canSupplierDeclineDeal(detail.value?.deal))
const canSubmitCredential = computed(() => viewMode.value === 'seller' && canSupplierSubmitCredential(detail.value?.deal))
const canViewCredential = computed(() => viewMode.value === 'buyer' && buyerCanViewCredential(detail.value?.deal))
const canConfirmDelivery = computed(() => viewMode.value === 'buyer' && buyerCanConfirmDelivery(detail.value?.deal))
const canReportDelivery = computed(() => viewMode.value === 'buyer' && buyerCanReportDelivery(detail.value?.deal))
const credentialFormValid = computed(() => credentialForm.host.trim().length > 0
  && Number(credentialForm.port) >= 1
  && Number(credentialForm.port) <= 65535
  && credentialForm.username.trim().length > 0
  && credentialForm.secret.trim().length > 0)
const timelineItems = computed(() => buildTimeline(detail.value))

function statusLabel(status: string) {
  const keys: Record<string, string> = {
    draft: 'statusRequirementSubmitted', published: 'statusRequirementSubmitted', quoting: 'statusPlanDiscussion', active: 'statusPlanDiscussion', quote_selected: 'statusConfirmed', pending_payment: 'statusConfirmed', processing: 'statusPlanDiscussion', coordination_requested: 'statusPlatformReview', buyer_selected: 'statusBuyerSelected', supplier_confirmed: 'statusSupplierConfirmed', platform_review: 'statusPlatformReview', credential_pending: 'statusCredentialPending', credential_submitted: 'statusCredentialSubmitted', credential_released: 'statusCredentialReleased', credential_rejected: 'statusCredentialRejected', delivery_disputed: 'statusDeliveryDisputed', supplier_declined: 'statusSupplierDeclined', platform_rejected: 'statusPlatformRejected', completed: 'statusCompletedMatch', cancelled: 'statusCancelled', expired: 'statusExpired', rejected: 'statusRejected', selected: 'statusConfirmed', declined: 'statusDeclined', withdrawn: 'statusWithdrawn',
  }
  return t(keys[status] || status)
}
function quoteAmount(quote: Pick<BuyRequestQuote, 'total_price' | 'currency'>) {
  const latest = latestQuoteRevision(quote as BuyRequestQuote)
  return formatQuoteAmount(latest.total_price, latest.currency, t('cardHour'))
}
function expiryText(value?: string) {
  if (!value) return t('noExpiration')
  const diff = new Date(value).getTime() - Date.now()
  if (diff <= 0) return t('expired')
  const hours = Math.ceil(diff / 3600000)
  return hours < 24 ? t('hoursRemaining', { count: hours }) : t('daysRemaining', { count: Math.ceil(hours / 24) })
}

function emptyQuoteForm(): MatchmakingQuoteFormValue {
  return { unitPrice: '', totalPrice: '', deliveryHours: '4', validityHours: '24', message: '' }
}

function latestQuoteRevision(quote: BuyRequestQuote): BuyRequestQuote | BuyRequestQuoteRevision {
  return quote.latest_revision || quote
}

function quoteRevisionCount(quote: BuyRequestQuote) {
  return Math.max(1, Number(quote.revision_count || quote.revisions?.length || quote.latest_revision?.revision_no || 1))
}

function quoteDeliveryText(quote: BuyRequestQuote) {
  const availableAt = latestQuoteRevision(quote).available_at || quote.available_at
  if (!availableAt) return t('deliveryTimeNegotiable')
  const date = new Date(availableAt)
  if (Number.isNaN(date.getTime())) return t('deliveryTimeNegotiable')
  const diffHours = Math.ceil((date.getTime() - Date.now()) / 3600000)
  return diffHours > 0 && diffHours <= 168
    ? t('deliveryWithinHours', { count: diffHours })
    : date.toLocaleString(i18n.locale, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function formatEventTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString(i18n.locale, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function buildTimeline(value: BuyRequestDetail | null) {
  if (!value?.deal) return []
  const stages = [
    { key: 'buyer_selected', label: t('timelinePlanSelected') },
    { key: 'supplier_confirmed', label: t('timelineSupplierConfirmed') },
    { key: 'platform_review', label: t('timelinePlatformReview') },
    { key: 'credential_released', label: t('timelineCredentialEscrow') },
    { key: 'completed', label: t('timelineConnectionConfirmed') },
  ]
  const statusPosition: Record<string, number> = {
    buyer_selected: 0,
    supplier_declined: 0,
    supplier_confirmed: 1,
    platform_review: 2,
    platform_rejected: 2,
    credential_pending: 3,
    credential_submitted: 3,
    credential_rejected: 3,
    credential_released: 3,
    delivery_disputed: 4,
    completed: 4,
    cancelled: 0,
  }
  const errorStatuses = new Set(['supplier_declined', 'platform_rejected', 'credential_rejected', 'delivery_disputed', 'cancelled'])
  const position = statusPosition[value.deal.status] ?? 0
  return stages.map((stage, index) => {
    const matchingEvent = [...(value.events || [])].reverse().find(event => event.status === stage.key || event.event_type === stage.key)
    const state = index < position ? 'complete' : index === position ? (errorStatuses.has(value.deal?.status || '') ? 'error' : 'current') : 'pending'
    return { ...stage, state, meta: formatEventTime(matchingEvent?.created_at) }
  })
}

function quotePayload(): BuyRequestQuotePayload | null {
  const totalPrice = Number(quoteForm.value.totalPrice)
  const unitPrice = Number(quoteForm.value.unitPrice)
  const deliveryHours = Number(quoteForm.value.deliveryHours)
  const validityHours = Number(quoteForm.value.validityHours)
  if (!(totalPrice > 0) || !(deliveryHours > 0) || !(validityHours > 0)) return null
  const editedQuote = editingQuoteId.value == null ? null : detail.value?.quotes.find(item => item.id === editingQuoteId.value)
  const currency = editedQuote ? latestQuoteRevision(editedQuote).currency : detail.value?.request.currency
  return {
    unit_price: unitPrice > 0 ? unitPrice : undefined,
    total_price: totalPrice,
    currency: currency || 'CNY',
    available_at: new Date(Date.now() + deliveryHours * 3600000).toISOString(),
    message: quoteForm.value.message.trim() || undefined,
    expires_in_hours: validityHours,
  }
}

async function load() {
  loading.value = true
  loadError.value = false
  try {
    if (viewMode.value === 'seller') {
      requests.value = await getBuyRequests(requestType.value, 'seller')
      Object.assign(summary, { active: 0, new_quotes: 0, pending_confirmation: 0 })
    } else {
      const [items, counts] = await Promise.all([getBuyRequests(requestType.value, 'buyer'), getBuyRequestSummary()])
      requests.value = items
      Object.assign(summary, counts)
    }
  } catch {
    loadError.value = true
  } finally { loading.value = false }
}
async function loadMarketModels() {
  try {
    marketModels.value = (await getMarketModels(true)).items.filter((item) => item.sources.includes('kai'))
    if (marketModels.value.length) {
      modelIndex.value = 0
      setModel(marketModels.value[0])
    }
  } catch {}
}
function setModel(item: MarketModel) {
  form.gpu_model = item.gpu_model
  form.gpu_variant = item.gpu_variant
}
function onModelChange(event: any) {
  modelIndex.value = Number(event.detail.value)
  const item = marketModels.value[modelIndex.value]
  if (item) setModel(item)
}
function onNeedHostingChange(event: any) { form.need_hosting = Boolean(event.detail.value) }
function onInvoiceChange(event: any) { form.invoice_required = Boolean(event.detail.value) }
function resetForm() {
  Object.assign(form, { gpu_model: '', gpu_variant: '', quantity: '1', gpu_hours: '', region: '', contact: '', phone: '', remark: '', need_hosting: false, invoice_required: false })
  billingIndex.value = 0
  expiryIndex.value = 2
}
function resetRequestIntent() { pendingRequestIntent.value = null }
function buildRequestPayload(): Omit<BuyRequestPayload, 'client_request_id'> {
  return {
    request_type: requestType.value,
    gpu_model: form.gpu_model,
    gpu_variant: form.gpu_variant || undefined,
    quantity: Number(form.quantity),
    gpu_hours: requestType.value === 'online' ? Number(form.gpu_hours) : undefined,
    currency: 'CNY',
    region: form.region || undefined,
    billing_mode: requestType.value === 'online' ? billingValues[billingIndex.value] : undefined,
    requirements: {
      product_id: inquiryContext.value?.product_id ?? null,
      supplier_id: inquiryContext.value?.supplier_id ?? null,
      source: inquiryContext.value?.source || 'direct_request',
      product_name: inquiryContext.value?.product_name || `${form.gpu_model}${form.gpu_variant ? ` ${form.gpu_variant}` : ''}`,
      remark: form.remark,
      need_hosting: form.need_hosting,
      invoice_required: form.invoice_required,
    },
    contact: form.contact.trim(),
    phone: form.phone.trim(),
    expires_in_hours: requestType.value === 'online' ? expiryValues[expiryIndex.value] : 24 * 7,
  }
}
function ensureRequestId(payload: Omit<BuyRequestPayload, 'client_request_id'>): string {
  pendingRequestIntent.value = ensureClientRequestIntent(
    pendingRequestIntent.value,
    payload,
    () => `buy-request-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`,
  )
  return pendingRequestIntent.value.requestId
}
function applyInquiryPrefill(prefill: InquiryRequestPrefill) {
  form.gpu_model = prefill.gpu_model
  form.gpu_variant = prefill.gpu_variant || ''
  form.quantity = String(Math.max(1, prefill.quantity || 1))
  form.gpu_hours = String(Math.max(1, prefill.gpu_hours || 1))
  form.region = prefill.region || ''
}
async function openForm() {
  if (viewMode.value !== 'buyer' || !commerce.matchmakingEnabled) {
    if (!commerce.matchmakingEnabled) uni.showToast({ title: t('dataUnavailable'), icon: 'none' })
    return
  }
  resetRequestIntent()
  resetForm()
  inquiryContext.value = readInquiryRequestPrefill()
  if (inquiryContext.value) {
    applyInquiryPrefill(inquiryContext.value)
  } else {
    if (!marketModels.value.length) await loadMarketModels()
    if (marketModels.value.length) setModel(marketModels.value[0])
  }
  showForm.value = true
}
function closeForm() { resetRequestIntent(); showForm.value = false }
async function submitRequest() {
  if (submitting.value || viewMode.value !== 'buyer' || !commerce.matchmakingEnabled) return
  if (!form.gpu_model || Number(form.quantity) <= 0) { uni.showToast({ title: t('completeRequiredFields'), icon: 'none' }); return }
  if (requestType.value === 'online' && Number(form.gpu_hours) <= 0) { uni.showToast({ title: t('enterGpuHours'), icon: 'none' }); return }
  if (!form.contact.trim() || !form.phone.trim()) { uni.showToast({ title: t('completeContactInfo'), icon: 'none' }); return }
  const phone = normalizeBuyRequestContactPhone(form.phone)
  if (!phone) { uni.showToast({ title: t('enterValidContactPhone'), icon: 'none' }); return }
  form.phone = phone
  submitting.value = true
  try {
    const payload = buildRequestPayload()
    await createBuyRequest({ ...payload, client_request_id: ensureRequestId(payload) })
    resetRequestIntent()
    uni.showToast({ title: t('requestPublished'), icon: 'success' })
    clearInquiryRequestPrefill()
    inquiryContext.value = null
    composeRequested.value = false
    showForm.value = false
    await load()
  } finally { submitting.value = false }
}
async function setRequestTab(value: number) { requestTab.value = value; await load() }
async function setViewTab(value: number) {
  const next: BuyRequestView = value === 0 && sellerViewAvailable.value ? 'seller' : 'buyer'
  if (viewMode.value === next) return
  viewMode.value = next
  showForm.value = false
  detail.value = null
  requests.value = []
  await load()
}
function isOwnRequest(item: Pick<BuyRequestItem, 'is_own' | 'user_id'>) {
  if (typeof item.is_own === 'boolean') return item.is_own
  return Number(item.user_id) === Number(userStore.userInfo?.id)
}
function canSelectQuote(quote: BuyRequestQuote) {
  return viewMode.value === 'buyer' && Boolean(detail.value && canBuyerSelectQuote({
    matchmakingEnabled: commerce.matchmakingEnabled,
    directTradeEnabled: commerce.directTradeEnabled,
    isOwnRequest: isOwnRequest(detail.value.request),
    requestStatus: detail.value.request.status,
    quote,
    deal: detail.value.deal,
  }))
}
function canBuyerCounter(quote: BuyRequestQuote) {
  return viewMode.value === 'buyer' && Boolean(detail.value && canCounterQuote({
    matchmakingEnabled: commerce.matchmakingEnabled,
    role: 'buyer',
    isOwnRequest: isOwnRequest(detail.value.request),
    requestStatus: detail.value.request.status,
    quote,
    deal: detail.value.deal,
  }))
}
function confirmQuoteSelection(quote: BuyRequestQuote) {
  if (!canSelectQuote(quote) || selectingQuoteId.value !== null || !detail.value) return
  const matchmaking = commerce.matchmakingEnabled
  uni.showModal({
    title: t(matchmaking ? 'requestPlatformCoordinationTitle' : 'confirmQuoteSelection'),
    content: t(matchmaking ? 'requestPlatformCoordinationHint' : 'quoteSelectionHint'),
    confirmText: t(matchmaking ? 'requestPlatformCoordination' : 'selectQuote'),
    success: (result) => {
      if (result.confirm) void selectQuote(quote, matchmaking)
    },
  })
}
async function selectQuote(quote: BuyRequestQuote, matchmaking: boolean) {
  const requestId = detail.value?.request.id
  if (!requestId || !canSelectQuote(quote) || selectingQuoteId.value !== null) return
  selectingQuoteId.value = quote.id
  try {
    await selectBuyRequestQuote(requestId, quote.id)
    const refreshedDetail = await getBuyRequestDetail(requestId)
    detail.value = refreshedDetail
    await load()
    uni.showToast({ title: t(matchmaking ? 'platformCoordinationRequested' : 'quoteSelected'), icon: 'success' })
  } finally {
    selectingQuoteId.value = null
  }
}

function beginQuoteEdit(quote: BuyRequestQuote, role: 'buyer' | 'seller') {
  if (role === 'buyer' ? !canBuyerCounter(quote) : !canSellerRevise.value) return
  const latest = latestQuoteRevision(quote)
  const availableAt = latest.available_at || quote.available_at
  const deliveryHours = availableAt ? Math.max(1, Math.ceil((new Date(availableAt).getTime() - Date.now()) / 3600000)) : 4
  const expiresAt = latest.expires_at || quote.expires_at
  const validityHours = expiresAt ? Math.max(1, Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 3600000)) : 24
  editingQuoteId.value = quote.id
  quoteFormRole.value = role
  quoteForm.value = {
    unitPrice: latest.unit_price == null ? '' : String(latest.unit_price),
    totalPrice: String(latest.total_price),
    deliveryHours: String(deliveryHours),
    validityHours: String(validityHours),
    message: latest.message || '',
  }
}

function cancelQuoteEdit() {
  editingQuoteId.value = null
  quoteForm.value = emptyQuoteForm()
}

async function refreshDetail(requestId: number) {
  detail.value = await getBuyRequestDetail(requestId)
  if (canViewCredential.value) await loadReleasedCredential()
}

async function submitQuoteForm() {
  if (!detail.value || actionBusy.value) return
  const payload = quotePayload()
  if (!payload) {
    uni.showToast({ title: t('completeProposalFields'), icon: 'none' })
    return
  }
  const requestId = detail.value.request.id
  const quoteId = editingQuoteId.value
  if (quoteId === null && !canSellerSubmit.value) return
  actionBusy.value = true
  try {
    if (quoteId === null) await submitBuyRequestQuote(requestId, payload)
    else await counterBuyRequestQuote(requestId, quoteId, payload)
    cancelQuoteEdit()
    await refreshDetail(requestId)
    await load()
    uni.showToast({ title: t(quoteId === null ? 'proposalSubmitted' : 'proposalRevisionSubmitted'), icon: 'success' })
  } finally {
    actionBusy.value = false
  }
}

function confirmWithdrawQuote(quote: BuyRequestQuote) {
  if (!canSellerWithdraw.value || actionBusy.value || !detail.value) return
  uni.showModal({
    title: t('withdrawProposal'),
    content: t('withdrawProposalHint'),
    confirmText: t('confirmProposalWithdrawal'),
    success: result => { if (result.confirm) void withdrawQuote(quote) },
  })
}

async function withdrawQuote(quote: BuyRequestQuote) {
  if (!detail.value || actionBusy.value) return
  const requestId = detail.value.request.id
  actionBusy.value = true
  try {
    await withdrawBuyRequestQuote(requestId, quote.id)
    cancelQuoteEdit()
    await refreshDetail(requestId)
    await load()
    uni.showToast({ title: t('proposalWithdrawn'), icon: 'success' })
  } finally { actionBusy.value = false }
}

function confirmSupplierDecision(confirmed: boolean) {
  if (!detail.value?.deal || actionBusy.value) return
  if (confirmed ? !canSupplierConfirm.value : !canSupplierDecline.value) return
  uni.showModal({
    title: t(confirmed ? 'confirmResourceAvailable' : 'cannotProvideResource'),
    content: t(confirmed ? 'confirmResourceAvailableHint' : 'declineResourceHint'),
    confirmText: t('confirm'),
    success: result => { if (result.confirm) void submitSupplierDecision(confirmed) },
  })
}

async function submitSupplierDecision(confirmed: boolean) {
  if (!detail.value?.deal || actionBusy.value) return
  const requestId = detail.value.request.id
  const dealId = detail.value.deal.id
  actionBusy.value = true
  try {
    if (confirmed) await confirmBuyRequestDealBySupplier(requestId, dealId)
    else await declineBuyRequestDealBySupplier(requestId, dealId)
    await refreshDetail(requestId)
    await load()
    uni.showToast({ title: t(confirmed ? 'resourceAvailabilityConfirmed' : 'resourceAvailabilityDeclined'), icon: 'success' })
  } finally { actionBusy.value = false }
}

async function submitCredential() {
  if (!detail.value?.deal || !canSubmitCredential.value || !credentialFormValid.value || actionBusy.value) return
  const requestId = detail.value.request.id
  actionBusy.value = true
  try {
    await submitBuyRequestCredential(requestId, detail.value.deal.id, {
      host: credentialForm.host.trim(),
      port: Number(credentialForm.port),
      username: credentialForm.username.trim(),
      auth_type: credentialTypeIndex.value === 0 ? 'password' : 'private_key',
      secret: credentialForm.secret.trim(),
      note: credentialForm.note.trim() || undefined,
    })
    Object.assign(credentialForm, { host: '', port: '22', username: '', secret: '', note: '' })
    await refreshDetail(requestId)
    uni.showToast({ title: t('credentialSubmittedToPlatform'), icon: 'success' })
  } finally { actionBusy.value = false }
}

async function loadReleasedCredential() {
  if (!detail.value?.deal || !canViewCredential.value || credentialLoading.value) return
  credentialLoading.value = true
  credentialError.value = false
  try {
    releasedCredential.value = await getBuyRequestCredential(detail.value.request.id, detail.value.deal.id)
  } catch {
    credentialError.value = true
    releasedCredential.value = null
  } finally { credentialLoading.value = false }
}

function copyCredential() {
  if (!releasedCredential.value) return
  const credential = releasedCredential.value
  const command = `ssh -p ${credential.port} ${credential.username}@${credential.host}`
  const secretLabel = t(credential.auth_type === 'password' ? 'sshPassword' : 'sshPrivateKey')
  uni.setClipboardData({ data: `${command}\n${secretLabel}: ${credential.secret || ''}${credential.note ? `\n${credential.note}` : ''}`, success: () => uni.showToast({ title: t('credentialCopied'), icon: 'success' }) })
}

function confirmCredentialUsable() {
  if (!detail.value?.deal || !canConfirmDelivery.value || actionBusy.value) return
  uni.showModal({
    title: t('confirmConnectionUsable'),
    content: t('confirmConnectionUsableHint'),
    confirmText: t('confirm'),
    success: result => { if (result.confirm) void submitDeliveryConfirmation() },
  })
}

async function submitDeliveryConfirmation() {
  if (!detail.value?.deal || actionBusy.value) return
  const requestId = detail.value.request.id
  actionBusy.value = true
  try {
    await confirmBuyRequestDelivery(requestId, detail.value.deal.id)
    await refreshDetail(requestId)
    await load()
    uni.showToast({ title: t('connectionConfirmed'), icon: 'success' })
  } finally { actionBusy.value = false }
}

function openIssueForm() { if (canReportDelivery.value) showIssueForm.value = true }

async function reportCredentialIssue() {
  if (!detail.value?.deal || !canReportDelivery.value || !issueReason.value.trim() || actionBusy.value) return
  const requestId = detail.value.request.id
  actionBusy.value = true
  try {
    await reportBuyRequestDelivery(requestId, detail.value.deal.id, issueReason.value.trim())
    issueReason.value = ''
    showIssueForm.value = false
    await refreshDetail(requestId)
    await load()
    uni.showToast({ title: t('connectionIssueSubmitted'), icon: 'success' })
  } finally { actionBusy.value = false }
}

async function openDetail(item: BuyRequestItem) {
  detailLoading.value = true
  credentialError.value = false
  releasedCredential.value = null
  editingQuoteId.value = null
  quoteFormRole.value = viewMode.value === 'seller' ? 'seller' : 'buyer'
  quoteForm.value = emptyQuoteForm()
  try {
    await refreshDetail(item.id)
  } catch {
    uni.showToast({ title: t('requestDetailLoadFailed'), icon: 'none' })
  } finally { detailLoading.value = false }
}
function closeDetail() {
  detail.value = null
  editingQuoteId.value = null
  releasedCredential.value = null
  showIssueForm.value = false
  issueReason.value = ''
}
onLoad(async (options) => {
  composeRequested.value = String(options?.compose || '') === '1'
  requestedInitialView.value = String(options?.view || '') === 'seller' ? 'seller' : 'buyer'
  if (requestedInitialView.value === 'seller' && !composeRequested.value) {
    if (userStore.isLogin && !userStore.userInfo) {
      try { await userStore.fetchProfile() } catch {}
    }
    if (sellerViewAvailable.value) {
      viewMode.value = 'seller'
      viewInitialized.value = true
      showForm.value = false
      await load()
    }
  }
})
onShow(async () => {
  i18n.updateTabBar()
  if (userStore.isLogin && !userStore.userInfo) {
    try { await userStore.fetchProfile() } catch {}
  }
  const pendingInquiry = readInquiryRequestPrefill()
  if (composeRequested.value || pendingInquiry) {
    viewMode.value = 'buyer'
    viewInitialized.value = true
  } else if (!viewInitialized.value) {
    viewMode.value = requestedInitialView.value === 'seller' && sellerViewAvailable.value ? 'seller' : 'buyer'
    viewInitialized.value = true
  } else if (viewMode.value === 'seller' && !sellerViewAvailable.value) {
    viewMode.value = 'buyer'
  }
  await load()
  if (composeRequested.value || pendingInquiry) {
    if (!showForm.value) await openForm()
  } else if (viewMode.value === 'buyer' && !marketModels.value.length) {
    await loadMarketModels()
  }
})
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(80rpx + var(--safe-bottom)); }
.view-switch { margin-bottom: 18rpx; }
.summary-strip { display: flex; padding: 26rpx 0; margin-bottom: 18rpx; border-bottom: 1rpx solid var(--divider); }
.summary-item { flex: 1; text-align: center; }
.summary-item + .summary-item { border-left: 1rpx solid var(--divider); }
.summary-value { display: block; color: var(--text); font-size: 36rpx; font-weight: 800; font-variant-numeric: tabular-nums; }
.summary-value.primary { color: var(--primary); }
.summary-label { display: block; color: var(--text-sub); font-size: 20rpx; margin-top: 5rpx; }
.request-card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); padding: 28rpx; margin-top: 16rpx; }
.request-card.own-request { background: var(--bg-2); }
.request-head { display: flex; justify-content: space-between; align-items: center; }
.request-flags { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 10rpx; }
.own-request-badge { color: var(--text-sub); background: var(--bg-2); border: 1rpx solid var(--border); border-radius: 999rpx; padding: 6rpx 12rpx; font-size: 18rpx; font-weight: 650; }
.type-label { color: var(--primary); font-size: 20rpx; font-weight: 650; }
.type-label.offline { color: var(--text-sub); }
.status-label { color: var(--text-sub); font-size: 20rpx; }
.status-label.quoting, .status-label.active, .status-label.quote_selected, .status-label.pending_payment, .status-label.processing, .status-label.selected { color: var(--primary); }
.status-label.completed { color: var(--up); }
.status-label.expired, .status-label.rejected, .status-label.cancelled { color: var(--down); }
.request-model { display: block; color: var(--text); font-size: 32rpx; font-weight: 750; margin-top: 17rpx; }
.request-specs { display: flex; flex-wrap: wrap; gap: 16rpx; color: var(--text-sub); font-size: 21rpx; margin-top: 10rpx; }
.request-bottom { display: flex; justify-content: space-between; align-items: flex-end; padding-top: 22rpx; margin-top: 22rpx; border-top: 1rpx solid var(--divider); }
.budget-label, .quote-label { display: block; color: var(--text-sub); font-size: 19rpx; }
.budget-value { display: block; color: var(--text); font-size: 29rpx; font-weight: 750; margin-top: 5rpx; }
.quote-box { text-align: right; }
.quote-value { display: block; color: var(--primary); font-size: 28rpx; font-weight: 750; }
.expiry { display: block; color: var(--text-dim); font-size: 19rpx; margin-top: 12rpx; text-align: right; }
.post-button { display: flex; justify-content: center; align-items: center; gap: 8rpx; margin-top: 22rpx; background: var(--primary); color: #fff; border-radius: var(--radius); padding: 25rpx; font-size: 27rpx; font-weight: 650; }
.plus { font-size: 32rpx; }
.empty-card { display: flex; flex-direction: column; align-items: center; color: var(--primary); padding: 80rpx 30rpx; margin-top: 18rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); text-align: center; }
.empty-title { color: var(--text); font-size: 28rpx; font-weight: 650; margin-top: 18rpx; }
.empty-copy { color: var(--text-sub); font-size: 21rpx; line-height: 1.55; margin-top: 10rpx; }
.empty-action { color: #fff; background: var(--primary); padding: 18rpx 34rpx; border-radius: 12rpx; font-size: 24rpx; margin-top: 26rpx; }
.list-skeleton { margin-top: 18rpx; }
.sk-card { height: 260rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); margin-bottom: 16rpx; }
.mode-intro { margin-bottom: 22rpx; }
.mode-title { display: block; color: var(--text); font-size: 34rpx; font-weight: 750; }
.mode-copy { display: block; color: var(--text-sub); font-size: 22rpx; line-height: 1.55; margin-top: 8rpx; }
.inquiry-context { display: flex; align-items: center; justify-content: space-between; gap: 24rpx; padding: 24rpx 26rpx; margin-bottom: 18rpx; color: var(--text); background: var(--primary-soft); border: 1rpx solid var(--card-border); border-radius: var(--radius); }
.context-label { display: block; color: var(--primary); font-size: 19rpx; font-weight: 650; }
.context-title { display: block; margin-top: 6rpx; font-size: 27rpx; font-weight: 720; }
.context-meta { display: block; margin-top: 4rpx; color: var(--text-sub); font-size: 19rpx; }
.context-provider { flex-shrink: 0; max-width: 42%; text-align: right; color: var(--text-sub); font-size: 19rpx; }
.context-provider text { display: block; }
.context-provider text + text { margin-top: 5rpx; color: var(--text); font-weight: 650; }
.form-section { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); padding: 28rpx; }
.field { margin-bottom: 28rpx; }
.field:last-child { margin-bottom: 0; }
.field.two-col { display: flex; gap: 20rpx; }
.half { flex: 1; min-width: 0; }
.field-label { display: block; color: var(--text-sub); font-size: 21rpx; margin-bottom: 11rpx; }
.field-input, .picker-value { box-sizing: border-box; width: 100%; height: 76rpx; padding: 0 20rpx; color: var(--text); background: var(--bg); border: 1rpx solid var(--border); border-radius: 12rpx; font-size: 25rpx; }
.picker-value { display: flex; justify-content: space-between; align-items: center; }
.readonly-value { color: var(--text-sub); background: var(--bg-2); }
.picker-arrow { color: var(--text-dim); }
.placeholder { color: var(--text-dim); }
.field-textarea { box-sizing: border-box; width: 100%; height: 170rpx; padding: 18rpx 20rpx; color: var(--text); background: var(--bg); border: 1rpx solid var(--border); border-radius: 12rpx; font-size: 24rpx; line-height: 1.5; }
.field-textarea.short { height: 120rpx; }
.option-row { display: flex; align-items: center; justify-content: space-between; padding: 20rpx 0; margin-bottom: 18rpx; border-bottom: 1rpx solid var(--divider); }
.option-title { display: block; color: var(--text); font-size: 24rpx; font-weight: 600; }
.option-copy { display: block; color: var(--text-sub); font-size: 19rpx; margin-top: 5rpx; }
.form-actions { display: flex; gap: 18rpx; margin-top: 20rpx; }
.cancel-button, .submit-button { flex: 1; text-align: center; padding: 24rpx; border-radius: var(--radius); font-size: 26rpx; font-weight: 650; }
.cancel-button { color: var(--text); border: 1rpx solid var(--border); background: var(--card); }
.submit-button { color: #fff; background: var(--primary); }
.submit-button.disabled { opacity: .5; }
.sheet-mask { position: fixed; inset: 0; z-index: 90; background: rgba(10, 20, 24, .48); display: flex; align-items: flex-end; }
.loading-mask { align-items: center; justify-content: center; }
.detail-loading { min-width: 260rpx; display: flex; flex-direction: column; align-items: center; gap: 18rpx; padding: 34rpx; color: var(--text-sub); background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); font-size: 22rpx; }
.loading-spinner { width: 38rpx; height: 38rpx; border: 4rpx solid var(--divider); border-top-color: var(--primary); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.detail-sheet { width: 100%; max-height: 86vh; background: var(--bg); border-radius: 28rpx 28rpx 0 0; padding: 14rpx 32rpx calc(30rpx + var(--safe-bottom)); }
.sheet-handle { width: 72rpx; height: 7rpx; border-radius: 4rpx; background: var(--text-dim); opacity: .45; margin: 0 auto 18rpx; }
.sheet-head { display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: 20rpx; }
.sheet-title { display: block; color: var(--text); font-size: 31rpx; font-weight: 750; }
.sheet-eyebrow { display: block; margin-bottom: 5rpx; color: var(--text-sub); font-size: 18rpx; font-weight: 650; }
.sheet-sub { display: block; color: var(--primary); font-size: 20rpx; margin-top: 5rpx; }
.sheet-close { color: var(--text-sub); font-size: 42rpx; padding: 0 6rpx; }
.sheet-scroll { max-height: 68vh; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14rpx; }
.detail-cell { background: var(--card); border: 1rpx solid var(--border); border-radius: 12rpx; padding: 20rpx; }
.detail-label { display: block; color: var(--text-sub); font-size: 19rpx; }
.detail-value { display: block; color: var(--text); font-size: 25rpx; font-weight: 650; margin-top: 5rpx; }
.detail-remark { display: block; color: var(--text-sub); font-size: 22rpx; line-height: 1.55; margin-top: 18rpx; }
.seller-detail-note { margin-top: 22rpx; padding: 22rpx; color: var(--text-sub); background: var(--card); border: 1rpx solid var(--border); border-radius: 12rpx; font-size: 22rpx; line-height: 1.55; }
.privacy-note { margin-top: 22rpx; padding: 20rpx 22rpx; background: var(--primary-soft); border: 1rpx solid var(--card-border); border-radius: 12rpx; }
.privacy-note text { display: block; color: var(--text); font-size: 22rpx; font-weight: 650; }
.privacy-note text + text { margin-top: 5rpx; color: var(--text-sub); font-size: 19rpx; font-weight: 400; line-height: 1.5; }
.section-title { display: block; color: var(--text); font-size: 27rpx; font-weight: 700; margin: 28rpx 0 14rpx; }
.section-title.compact { margin: 4rpx 0 0; }
.section-kicker { display: block; color: var(--primary); font-size: 18rpx; font-weight: 700; }
.quote-empty { color: var(--text-sub); font-size: 22rpx; padding: 28rpx; background: var(--card); border-radius: 12rpx; text-align: center; }
.quote-card { padding: 22rpx; margin-bottom: 12rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: 12rpx; }
.quote-main { display: flex; justify-content: space-between; align-items: flex-start; gap: 20rpx; }
.quote-supplier { display: block; color: var(--text); font-size: 24rpx; font-weight: 650; }
.revision-meta { display: block; margin-top: 5rpx; color: var(--primary); font-size: 18rpx; }
.quote-message { display: block; color: var(--text-sub); font-size: 20rpx; line-height: 1.5; margin-top: 14rpx; }
.quote-price { display: block; color: var(--text); font-size: 26rpx; font-weight: 750; }
.quote-status { display: block; color: var(--primary); font-size: 19rpx; line-height: 1.45; margin-top: 10rpx; }
.quote-meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12rpx; margin-top: 18rpx; }
.quote-meta-grid view { padding: 14rpx 16rpx; background: var(--bg); border-radius: 10rpx; }
.quote-meta-grid text { display: block; color: var(--text-sub); font-size: 18rpx; }
.quote-meta-grid text + text { margin-top: 4rpx; color: var(--text); font-size: 20rpx; font-weight: 650; }
.quote-actions { display: flex; justify-content: flex-end; gap: 12rpx; margin-top: 18rpx; }
.primary-action, .secondary-action, .danger-action { min-height: 58rpx; display: inline-flex; align-items: center; justify-content: center; padding: 0 18rpx; border-radius: 10rpx; font-size: 20rpx; font-weight: 700; }
.primary-action { color: #fff; background: var(--primary); }
.secondary-action { color: var(--primary); background: var(--primary-soft); border: 1rpx solid var(--card-border); }
.danger-action { color: var(--down); background: var(--card); border: 1rpx solid var(--down); }
.primary-action.disabled, .secondary-action.disabled, .danger-action.disabled { opacity: .45; }
.primary-action.full { width: 100%; box-sizing: border-box; margin-top: 4rpx; }
.secondary-action.small { min-height: 50rpx; padding: 0 14rpx; font-size: 18rpx; }
.action-panel, .inline-form { padding: 22rpx; margin-top: 16rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: 12rpx; }
.inline-form { margin-top: 18rpx; background: var(--bg-2); }
.inline-form-title { display: block; color: var(--text); font-size: 24rpx; font-weight: 700; }
.form-hint { display: block; margin-top: 6rpx; color: var(--text-sub); font-size: 20rpx; line-height: 1.5; }
.compact-panel { margin-top: 20rpx; }
.deal-section { margin-top: 26rpx; padding-top: 4rpx; border-top: 1rpx solid var(--divider); }
.deal-head { display: flex; align-items: flex-start; justify-content: space-between; margin-top: 22rpx; }
.deal-id { color: var(--text-dim); font-size: 19rpx; }
.timeline { margin-top: 18rpx; padding: 20rpx 20rpx 4rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: 12rpx; }
.timeline-item { display: flex; min-height: 76rpx; }
.timeline-rail { width: 28rpx; display: flex; flex-direction: column; align-items: center; margin-right: 14rpx; }
.timeline-dot { width: 16rpx; height: 16rpx; flex-shrink: 0; margin-top: 5rpx; border: 3rpx solid var(--text-dim); border-radius: 50%; background: var(--card); }
.timeline-line { width: 2rpx; flex: 1; margin-top: 5rpx; background: var(--divider); }
.timeline-copy text { display: block; color: var(--text-sub); font-size: 21rpx; }
.timeline-copy text + text { margin-top: 4rpx; color: var(--text-dim); font-size: 17rpx; }
.timeline-item.complete .timeline-dot, .timeline-item.current .timeline-dot { border-color: var(--primary); background: var(--primary); }
.timeline-item.complete .timeline-line { background: var(--primary); }
.timeline-item.complete .timeline-copy text, .timeline-item.current .timeline-copy text { color: var(--text); font-weight: 650; }
.timeline-item.error .timeline-dot { border-color: var(--down); background: var(--down); }
.timeline-item.error .timeline-copy text { color: var(--down); font-weight: 650; }
.credential-form .field { margin-top: 20rpx; margin-bottom: 0; }
.credential-card { margin-top: 18rpx; padding: 22rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: 12rpx; }
.credential-card.muted { color: var(--text-sub); font-size: 20rpx; }
.credential-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16rpx; }
.credential-title { display: block; max-width: 430rpx; margin-top: 5rpx; color: var(--text); font-size: 22rpx; font-weight: 700; word-break: break-all; }
.credential-secret { margin-top: 18rpx; padding: 16rpx; background: var(--bg); border-radius: 10rpx; }
.credential-secret text { display: block; color: var(--text-sub); font-size: 18rpx; }
.credential-secret text + text { margin-top: 6rpx; color: var(--text); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 20rpx; line-height: 1.45; word-break: break-all; }
.credential-note { display: block; margin-top: 12rpx; color: var(--text-sub); font-size: 19rpx; line-height: 1.5; }
</style>
