<template>
  <view class="page">
    <AppNavBar :title="t(showForm ? 'postBuyRequest' : 'myBuyRequests')" />
    <view class="shell">
      <template v-if="!showForm">
        <view class="summary-strip">
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

        <view v-if="isSupplierMode" class="view-switch">
          <view class="view-item" :class="{ active: viewMode === 'buyer' }" @tap="setView('buyer')">{{ t('buyerView') }}</view>
          <view class="view-item" :class="{ active: viewMode === 'seller' }" @tap="setView('seller')">{{ t('sellerView') }}</view>
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
          <text class="empty-title">{{ t(viewMode === 'seller' ? 'noOpenRequests' : 'noBuyRequests') }}</text>
          <text class="empty-copy">{{ t(requestType === 'online' ? 'onlineRequestHint' : 'offlineRequestHint') }}</text>
          <view v-if="viewMode === 'buyer'" class="empty-action" @tap="openForm">{{ t('postBuyRequest') }}</view>
        </view>

        <view v-for="item in requests" :key="item.id" class="request-card" @tap="openDetail(item)">
          <view class="request-head">
            <view class="type-label" :class="item.request_type">{{ t(item.request_type === 'online' ? 'onlineRequest' : 'offlineRequest') }}</view>
            <text class="status-label" :class="item.status">{{ statusLabel(item.status) }}</text>
          </view>
          <text class="request-model">{{ item.gpu_model }}<text v-if="item.gpu_variant"> {{ item.gpu_variant }}</text></text>
          <view class="request-specs">
            <text>{{ t('gpuQuantityValue', { count: item.quantity }) }}</text>
            <text v-if="item.gpu_hours">{{ t('gpuHoursValue', { count: item.gpu_hours }) }}</text>
            <text v-if="item.region">{{ tr(item.region) }}</text>
          </view>
          <view class="request-bottom">
            <view>
              <text class="budget-label">{{ item.max_unit_price != null ? t('maxUnitPrice') : t('totalBudget') }}</text>
              <text class="budget-value">{{ requestBudget(item) }}</text>
            </view>
            <view class="quote-box">
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

        <view class="form-section">
          <view class="field">
            <text class="field-label">{{ t('gpuModel') }}</text>
            <picker v-if="marketModels.length" :range="modelLabels" :value="modelIndex" @change="onModelChange">
              <view class="picker-value">{{ modelLabels[modelIndex] || t('selectGpuModel') }}<text class="picker-arrow">⌄</text></view>
            </picker>
            <input v-else v-model="form.gpu_model" class="field-input" :placeholder="t('enterGpuModel')" placeholder-class="placeholder" />
          </view>
          <view class="field two-col">
            <view class="half">
              <text class="field-label">{{ t('quantity') }}</text>
              <input v-model="form.quantity" type="number" class="field-input" :placeholder="t('enterQuantity')" placeholder-class="placeholder" />
            </view>
            <view class="half">
              <text class="field-label">{{ requestType === 'online' ? t('totalGpuHours') : t('totalBudget') }}</text>
              <input v-if="requestType === 'online'" v-model="form.gpu_hours" type="number" class="field-input" :placeholder="t('enterGpuHours')" placeholder-class="placeholder" />
              <input v-else v-model="form.budget" type="digit" class="field-input" :placeholder="t('enterBudget')" placeholder-class="placeholder" />
            </view>
          </view>
          <view class="field">
            <text class="field-label">{{ t('regionRequirement') }}</text>
            <input v-model="form.region" class="field-input" :placeholder="t('regionOptional')" placeholder-class="placeholder" />
          </view>

          <template v-if="requestType === 'online'">
            <view class="market-reference">
              <view>
                <text class="reference-label">{{ t('currentMarketMedian') }}</text>
                <text class="reference-time">{{ marketReferenceTime }}</text>
              </view>
              <text class="reference-price">{{ marketReference == null ? '--' : cardHourRate(marketReference) }}</text>
              <view v-if="marketReference != null" class="reference-action" @tap="useMarketPrice">{{ t('useMarketMedian') }}</view>
            </view>
            <view class="field">
              <text class="field-label">{{ t('maxUnitPrice') }}</text>
              <input v-model="form.max_unit_price" type="digit" class="field-input" :placeholder="t('enterMaxUnitPrice')" placeholder-class="placeholder" />
            </view>
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
            <view class="field two-col">
              <view class="half">
                <text class="field-label">{{ t('contactName') }}</text>
                <input v-model="form.contact" class="field-input" :placeholder="t('enterContactName')" placeholder-class="placeholder" />
              </view>
              <view class="half">
                <text class="field-label">{{ t('contactPhone') }}</text>
                <input v-model="form.phone" type="number" class="field-input" :placeholder="t('enterContactPhone')" placeholder-class="placeholder" />
              </view>
            </view>
          </template>

          <view class="field">
            <text class="field-label">{{ t('additionalRequirements') }}</text>
            <textarea v-model="form.remark" class="field-textarea" :placeholder="t('requirementsPlaceholder')" placeholder-class="placeholder" maxlength="500" />
          </view>
        </view>

        <view class="form-actions">
          <view class="cancel-button" @tap="closeForm">{{ t('cancel') }}</view>
          <view class="submit-button" :class="{ disabled: submitting }" @tap="submitRequest">{{ t(submitting ? 'submitting' : 'publishRequest') }}</view>
        </view>
      </template>
    </view>

    <view v-if="detail" class="sheet-mask" @tap="closeDetail">
      <view class="detail-sheet" @tap.stop>
        <view class="sheet-handle"></view>
        <view class="sheet-head">
          <view><text class="sheet-title">{{ detail.request.gpu_model }} {{ detail.request.gpu_variant }}</text><text class="sheet-sub">{{ statusLabel(detail.request.status) }}</text></view>
          <text class="sheet-close" @tap="closeDetail">×</text>
        </view>
        <scroll-view scroll-y class="sheet-scroll">
          <view class="detail-grid">
            <view class="detail-cell"><text class="detail-label">{{ t('quantity') }}</text><text class="detail-value">{{ detail.request.quantity }}</text></view>
            <view class="detail-cell"><text class="detail-label">{{ t('totalBudget') }}</text><text class="detail-value">{{ requestBudget(detail.request) }}</text></view>
            <view class="detail-cell"><text class="detail-label">{{ t('region') }}</text><text class="detail-value">{{ detail.request.region ? tr(detail.request.region) : t('notLimited') }}</text></view>
            <view class="detail-cell"><text class="detail-label">{{ t('quotesReceived') }}</text><text class="detail-value">{{ detail.request.quote_count }}</text></view>
          </view>
          <text v-if="detail.request.requirements?.remark" class="detail-remark">{{ detail.request.requirements.remark }}</text>

          <template v-if="viewMode === 'buyer'">
            <text class="section-title">{{ t('receivedQuotes') }}</text>
            <view v-if="!detail.quotes.length" class="quote-empty">{{ t('noQuotesYet') }}</view>
            <view v-for="quote in detail.quotes" :key="quote.id" class="quote-card">
              <view><text class="quote-supplier">{{ quote.supplier_name }}</text><text class="quote-message">{{ quote.message || t('noAdditionalMessage') }}</text></view>
              <view class="quote-right"><text class="quote-price">{{ money(quote.total_price) }}</text><view v-if="quote.status === 'active'" class="select-quote" @tap="selectQuote(quote.id)">{{ t('selectQuote') }}</view><text v-else class="quote-status">{{ statusLabel(quote.status) }}</text></view>
            </view>
          </template>

          <template v-else>
            <text class="section-title">{{ t('submitQuote') }}</text>
            <view v-if="detail.quotes.length" class="own-quote">{{ t('quoteAlreadySubmitted') }} {{ money(detail.quotes[0].total_price) }}</view>
            <view v-else class="quote-form">
              <view class="field two-col">
                <view class="half"><text class="field-label">{{ t('unitPriceOptional') }}</text><input v-model="quoteForm.unit_price" type="digit" class="field-input" :placeholder="t('unitPrice')" placeholder-class="placeholder" /></view>
                <view class="half"><text class="field-label">{{ t('totalQuote') }}</text><input v-model="quoteForm.total_price" type="digit" class="field-input" :placeholder="t('enterTotalQuote')" placeholder-class="placeholder" /></view>
              </view>
              <view class="field"><text class="field-label">{{ t('quoteMessage') }}</text><textarea v-model="quoteForm.message" class="field-textarea short" :placeholder="t('quoteMessagePlaceholder')" placeholder-class="placeholder" /></view>
              <view class="submit-quote" @tap="submitQuote">{{ t('submitQuote') }}</view>
            </view>
          </template>
        </scroll-view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import {
  createBuyRequest,
  createBuyRequestQuote,
  getBuyRequestDetail,
  getBuyRequests,
  getBuyRequestSummary,
  selectBuyRequestQuote,
  type BuyRequestItem,
  type BuyRequestQuote,
} from '@/api/buy-request'
import { getLatestMarket, getMarketModels, type MarketModel } from '@/api/market'
import AppNavBar from '@/components/AppNavBar.vue'
import SegmentedControl from '@/components/SegmentedControl.vue'
import AppIcon from '@/components/AppIcon.vue'
import { useUserStore } from '@/store/user'
import { useI18nStore } from '@/store/i18n'
import { fmtCH, fmtCHr, formatNumberInput, fromCardHours, toCardHours } from '@/utils/format'

const userStore = useUserStore()
const i18n = useI18nStore()
const { t, tr } = i18n
const requestTab = ref(0)
const viewMode = ref<'buyer' | 'seller'>('buyer')
const requests = ref<BuyRequestItem[]>([])
const summary = reactive({ active: 0, new_quotes: 0, pending_confirmation: 0 })
const loading = ref(false)
const loadError = ref(false)
const showForm = ref(false)
const submitting = ref(false)
const marketModels = ref<MarketModel[]>([])
const modelIndex = ref(0)
const billingIndex = ref(0)
const expiryIndex = ref(2)
const marketReference = ref<number | null>(null)
const marketReferenceTime = ref('--')
const detail = ref<{ request: BuyRequestItem; quotes: BuyRequestQuote[] } | null>(null)
const quoteForm = reactive({ unit_price: '', total_price: '', message: '' })
const form = reactive({
  gpu_model: '', gpu_variant: '', quantity: '1', gpu_hours: '', max_unit_price: '', budget: '', region: '', contact: '', phone: '', remark: '', need_hosting: false, invoice_required: false,
})

const requestType = computed<'online' | 'offline'>(() => requestTab.value === 0 ? 'online' : 'offline')
const requestTabs = computed(() => [t('onlineRequest'), t('offlineRequest')])
const isSupplierMode = computed(() => userStore.role === 'supplier' && userStore.canSwitchRole)
const modelLabels = computed(() => marketModels.value.map((item) => `${item.gpu_model}${item.gpu_variant ? ` ${item.gpu_variant}` : ''}`))
const billingLabels = computed(() => [t('onDemand'), t('interruptible'), t('reserved')])
const billingValues = ['ondemand', 'bid', 'reserved']
const expiryLabels = computed(() => [t('oneHour'), t('sixHours'), t('twentyFourHours'), t('threeDays')])
const expiryValues = [1, 6, 24, 72]

function money(value: number) { return fmtCH(value) }
function cardHourRate(value: number) { return fmtCHr(value) }
function requestBudget(item: BuyRequestItem) {
  if (item.max_unit_price != null) return cardHourRate(item.max_unit_price)
  if (item.budget != null) return money(item.budget)
  return t('negotiable')
}
function statusLabel(status: string) {
  const keys: Record<string, string> = {
    draft: 'statusDraft', published: 'statusPublished', quoting: 'statusQuoting', quote_selected: 'statusQuoteSelected', pending_payment: 'statusPendingPayment', processing: 'statusProcessing', completed: 'statusCompleted', cancelled: 'statusCancelled', expired: 'statusExpired', rejected: 'statusRejected', active: 'statusActive', selected: 'statusSelected', declined: 'statusDeclined',
  }
  return t(keys[status] || status)
}
function expiryText(value?: string) {
  if (!value) return t('noExpiration')
  const diff = new Date(value).getTime() - Date.now()
  if (diff <= 0) return t('expired')
  const hours = Math.ceil(diff / 3600000)
  return hours < 24 ? t('hoursRemaining', { count: hours }) : t('daysRemaining', { count: Math.ceil(hours / 24) })
}

async function load() {
  loading.value = true
  loadError.value = false
  try {
    const [items, counts] = await Promise.all([getBuyRequests(requestType.value, viewMode.value), getBuyRequestSummary()])
    requests.value = items
    Object.assign(summary, counts)
  } catch {
    loadError.value = true
  } finally { loading.value = false }
}
async function loadMarketModels() {
  try {
    marketModels.value = (await getMarketModels(true)).items
    if (marketModels.value.length) {
      modelIndex.value = 0
      setModel(marketModels.value[0])
    }
  } catch {}
}
async function setModel(item: MarketModel) {
  form.gpu_model = item.gpu_model
  form.gpu_variant = item.gpu_variant
  try {
    const sources = item.sources.filter((source) => source !== 'wod')
    const market = await getLatestMarket(item.gpu_model, item.gpu_variant, sources.length ? sources : item.sources, true)
    marketReference.value = market.summary.median_price_cny
    marketReferenceTime.value = market.server_time ? new Date(market.server_time).toLocaleString() : '--'
  } catch { marketReference.value = null; marketReferenceTime.value = '--' }
}
function onModelChange(event: any) {
  modelIndex.value = Number(event.detail.value)
  const item = marketModels.value[modelIndex.value]
  if (item) setModel(item)
}
function onNeedHostingChange(event: any) { form.need_hosting = Boolean(event.detail.value) }
function onInvoiceChange(event: any) { form.invoice_required = Boolean(event.detail.value) }
function useMarketPrice() { if (marketReference.value != null) form.max_unit_price = formatNumberInput(toCardHours(marketReference.value)) }
function resetForm() {
  Object.assign(form, { gpu_model: '', gpu_variant: '', quantity: '1', gpu_hours: '', max_unit_price: '', budget: '', region: '', contact: '', phone: '', remark: '', need_hosting: false, invoice_required: false })
  billingIndex.value = 0
  expiryIndex.value = 2
  if (marketModels.value.length) setModel(marketModels.value[0])
}
async function openForm() { resetForm(); showForm.value = true; if (!marketModels.value.length) await loadMarketModels() }
function closeForm() { showForm.value = false }
async function submitRequest() {
  if (submitting.value) return
  if (!form.gpu_model || Number(form.quantity) <= 0) { uni.showToast({ title: t('completeRequiredFields'), icon: 'none' }); return }
  if (requestType.value === 'online' && Number(form.gpu_hours) <= 0) { uni.showToast({ title: t('enterGpuHours'), icon: 'none' }); return }
  if (requestType.value === 'offline' && (!form.contact || !form.phone)) { uni.showToast({ title: t('completeContactInfo'), icon: 'none' }); return }
  submitting.value = true
  try {
    await createBuyRequest({
      request_type: requestType.value,
      gpu_model: form.gpu_model,
      gpu_variant: form.gpu_variant || undefined,
      quantity: Number(form.quantity),
      gpu_hours: requestType.value === 'online' ? Number(form.gpu_hours) : undefined,
      max_unit_price: requestType.value === 'online' && form.max_unit_price ? fromCardHours(form.max_unit_price) : undefined,
      budget: requestType.value === 'offline' && form.budget ? fromCardHours(form.budget) : undefined,
      currency: 'CNY',
      region: form.region || undefined,
      billing_mode: requestType.value === 'online' ? billingValues[billingIndex.value] : undefined,
      requirements: { remark: form.remark, need_hosting: form.need_hosting, invoice_required: form.invoice_required },
      contact: requestType.value === 'offline' ? form.contact : undefined,
      phone: requestType.value === 'offline' ? form.phone : undefined,
      expires_in_hours: requestType.value === 'online' ? expiryValues[expiryIndex.value] : 24 * 7,
    })
    uni.showToast({ title: t('requestPublished'), icon: 'success' })
    showForm.value = false
    await load()
  } finally { submitting.value = false }
}
async function setView(value: 'buyer' | 'seller') { viewMode.value = value; await load() }
async function setRequestTab(value: number) { requestTab.value = value; await load() }
async function openDetail(item: BuyRequestItem) {
  try { detail.value = await getBuyRequestDetail(item.id) } catch {}
}
function closeDetail() { detail.value = null; Object.assign(quoteForm, { unit_price: '', total_price: '', message: '' }) }
async function selectQuote(quoteId: number) {
  if (!detail.value) return
  const confirmed = await new Promise<boolean>((resolve) => uni.showModal({ title: t('confirmQuoteSelection'), content: t('quoteSelectionHint'), confirmText: t('confirm'), cancelText: t('cancel'), success: (res) => resolve(res.confirm), fail: () => resolve(false) }))
  if (!confirmed) return
  await selectBuyRequestQuote(detail.value.request.id, quoteId)
  uni.showToast({ title: t('quoteSelected'), icon: 'success' })
  detail.value = await getBuyRequestDetail(detail.value.request.id)
  await load()
}
async function submitQuote() {
  if (!detail.value || Number(quoteForm.total_price) <= 0) { uni.showToast({ title: t('enterTotalQuote'), icon: 'none' }); return }
  await createBuyRequestQuote(detail.value.request.id, { unit_price: quoteForm.unit_price ? fromCardHours(quoteForm.unit_price) : undefined, total_price: fromCardHours(quoteForm.total_price), currency: 'CNY', message: quoteForm.message || undefined, expires_in_hours: 24 })
  uni.showToast({ title: t('quoteSubmitted'), icon: 'success' })
  detail.value = await getBuyRequestDetail(detail.value.request.id)
  await load()
}

onShow(async () => {
  i18n.updateTabBar()
  try { await userStore.fetchProfile() } catch {}
  if (!isSupplierMode.value) viewMode.value = 'buyer'
  await Promise.all([load(), loadMarketModels()])
})
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.shell { padding: 0 32rpx calc(80rpx + var(--safe-bottom)); }
.summary-strip { display: flex; padding: 26rpx 0; margin-bottom: 18rpx; border-bottom: 1rpx solid var(--divider); }
.summary-item { flex: 1; text-align: center; }
.summary-item + .summary-item { border-left: 1rpx solid var(--divider); }
.summary-value { display: block; color: var(--text); font-size: 36rpx; font-weight: 800; font-variant-numeric: tabular-nums; }
.summary-value.primary { color: var(--primary); }
.summary-label { display: block; color: var(--text-sub); font-size: 20rpx; margin-top: 5rpx; }
.view-switch { display: flex; margin-bottom: 18rpx; padding: 6rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: 14rpx; }
.view-item { flex: 1; text-align: center; color: var(--text-sub); font-size: 23rpx; padding: 13rpx; border-radius: 10rpx; }
.view-item.active { color: var(--primary); background: var(--primary-soft); font-weight: 650; }
.request-card { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); padding: 28rpx; margin-top: 16rpx; }
.request-head { display: flex; justify-content: space-between; align-items: center; }
.type-label { color: var(--primary); font-size: 20rpx; font-weight: 650; }
.type-label.offline { color: var(--text-sub); }
.status-label { color: var(--text-sub); font-size: 20rpx; }
.status-label.quoting, .status-label.quote_selected, .status-label.selected { color: var(--primary); }
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
.form-section { background: var(--card); border: 1rpx solid var(--border); border-radius: var(--radius); padding: 28rpx; }
.field { margin-bottom: 28rpx; }
.field:last-child { margin-bottom: 0; }
.field.two-col { display: flex; gap: 20rpx; }
.half { flex: 1; min-width: 0; }
.field-label { display: block; color: var(--text-sub); font-size: 21rpx; margin-bottom: 11rpx; }
.field-input, .picker-value { box-sizing: border-box; width: 100%; height: 76rpx; padding: 0 20rpx; color: var(--text); background: var(--bg); border: 1rpx solid var(--border); border-radius: 12rpx; font-size: 25rpx; }
.picker-value { display: flex; justify-content: space-between; align-items: center; }
.picker-arrow { color: var(--text-dim); }
.placeholder { color: var(--text-dim); }
.field-textarea { box-sizing: border-box; width: 100%; height: 170rpx; padding: 18rpx 20rpx; color: var(--text); background: var(--bg); border: 1rpx solid var(--border); border-radius: 12rpx; font-size: 24rpx; line-height: 1.5; }
.field-textarea.short { height: 120rpx; }
.market-reference { display: flex; align-items: center; gap: 14rpx; padding: 20rpx; margin-bottom: 28rpx; background: var(--primary-soft); border-radius: 12rpx; }
.reference-label { color: var(--text); font-size: 21rpx; display: block; }
.reference-time { color: var(--text-sub); font-size: 17rpx; display: block; margin-top: 4rpx; }
.reference-price { margin-left: auto; color: var(--primary); font-size: 28rpx; font-weight: 750; }
.reference-action { color: var(--primary); border: 1rpx solid var(--primary); border-radius: 10rpx; padding: 10rpx 14rpx; font-size: 19rpx; }
.option-row { display: flex; align-items: center; justify-content: space-between; padding: 20rpx 0; margin-bottom: 18rpx; border-bottom: 1rpx solid var(--divider); }
.option-title { display: block; color: var(--text); font-size: 24rpx; font-weight: 600; }
.option-copy { display: block; color: var(--text-sub); font-size: 19rpx; margin-top: 5rpx; }
.form-actions { display: flex; gap: 18rpx; margin-top: 20rpx; }
.cancel-button, .submit-button { flex: 1; text-align: center; padding: 24rpx; border-radius: var(--radius); font-size: 26rpx; font-weight: 650; }
.cancel-button { color: var(--text); border: 1rpx solid var(--border); background: var(--card); }
.submit-button { color: #fff; background: var(--primary); }
.submit-button.disabled { opacity: .5; }
.sheet-mask { position: fixed; inset: 0; z-index: 90; background: rgba(10, 20, 24, .48); display: flex; align-items: flex-end; }
.detail-sheet { width: 100%; max-height: 86vh; background: var(--bg); border-radius: 28rpx 28rpx 0 0; padding: 14rpx 32rpx calc(30rpx + var(--safe-bottom)); }
.sheet-handle { width: 72rpx; height: 7rpx; border-radius: 4rpx; background: var(--text-dim); opacity: .45; margin: 0 auto 18rpx; }
.sheet-head { display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: 20rpx; }
.sheet-title { display: block; color: var(--text); font-size: 31rpx; font-weight: 750; }
.sheet-sub { display: block; color: var(--primary); font-size: 20rpx; margin-top: 5rpx; }
.sheet-close { color: var(--text-sub); font-size: 42rpx; padding: 0 6rpx; }
.sheet-scroll { max-height: 68vh; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14rpx; }
.detail-cell { background: var(--card); border: 1rpx solid var(--border); border-radius: 12rpx; padding: 20rpx; }
.detail-label { display: block; color: var(--text-sub); font-size: 19rpx; }
.detail-value { display: block; color: var(--text); font-size: 25rpx; font-weight: 650; margin-top: 5rpx; }
.detail-remark { display: block; color: var(--text-sub); font-size: 22rpx; line-height: 1.55; margin-top: 18rpx; }
.section-title { display: block; color: var(--text); font-size: 27rpx; font-weight: 700; margin: 28rpx 0 14rpx; }
.quote-empty, .own-quote { color: var(--text-sub); font-size: 22rpx; padding: 28rpx; background: var(--card); border-radius: 12rpx; text-align: center; }
.quote-card { display: flex; justify-content: space-between; gap: 20rpx; padding: 22rpx; margin-bottom: 12rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: 12rpx; }
.quote-supplier { display: block; color: var(--text); font-size: 24rpx; font-weight: 650; }
.quote-message { display: block; color: var(--text-sub); font-size: 19rpx; margin-top: 6rpx; }
.quote-right { text-align: right; }
.quote-price { display: block; color: var(--text); font-size: 26rpx; font-weight: 750; }
.select-quote, .submit-quote { color: #fff; background: var(--primary); border-radius: 10rpx; padding: 12rpx 18rpx; font-size: 20rpx; margin-top: 10rpx; text-align: center; }
.quote-status { display: block; color: var(--primary); font-size: 19rpx; margin-top: 8rpx; }
.quote-form { padding: 24rpx; background: var(--card); border: 1rpx solid var(--border); border-radius: 12rpx; }
.submit-quote { padding: 20rpx; font-size: 24rpx; }
</style>
