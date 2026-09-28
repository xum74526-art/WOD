import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { getOnboardingMine, type OnboardingItem } from '@/api/onboarding'
import {
  getDashboard,
  getSupplierDevices,
  getSupplierWallet,
  type SupplierDeviceItem,
} from '@/api/supplier'
import { getVerification, type VerificationInfo } from '@/api/verification'
import { useUserStore } from '@/store/user'

export type HostingDeviceStatus =
  | 'pending_review'
  | 'reviewing'
  | 'deploying'
  | 'running'
  | 'action_required'

export interface HostingDeviceItem {
  key: string
  source: 'application' | 'supplier'
  sourceId: number
  name: string
  model: string
  count: number
  status: HostingDeviceStatus
  location: string
  createdAt?: string
  note?: string
}

type SupplierDashboard = Awaited<ReturnType<typeof getDashboard>>
type SupplierWallet = Awaited<ReturnType<typeof getSupplierWallet>>

const STATUS_ORDER: HostingDeviceStatus[] = [
  'pending_review',
  'reviewing',
  'deploying',
  'running',
  'action_required',
]

function applicationStatus(status: string): HostingDeviceStatus {
  if (status === 'contacted') return 'reviewing'
  if (status === 'approved') return 'deploying'
  if (status === 'rejected') return 'action_required'
  return 'pending_review'
}

function applicationToDevice(item: OnboardingItem): HostingDeviceItem {
  return {
    key: `application-${item.id}`,
    source: 'application',
    sourceId: item.id,
    name: item.entity_type === 'company' ? 'companyHostingApplication' : 'personalHostingApplication',
    model: item.device_model,
    count: Math.max(Number(item.device_count) || 1, 1),
    status: applicationStatus(item.status),
    location: item.location || '',
    createdAt: item.created_at,
    note: item.review_note || item.remark,
  }
}

function supplierToDevice(item: SupplierDeviceItem): HostingDeviceItem {
  const needsAction = item.list_status !== 'on' || item.status === 'offline' || item.stock <= 0
  return {
    key: `supplier-${item.id}`,
    source: 'supplier',
    sourceId: item.id,
    name: item.name,
    model: item.gpu_model,
    count: Math.max(Number(item.stock) || 0, 1),
    status: needsAction ? 'action_required' : 'running',
    location: [item.region, item.city].filter((value) => value && value !== '-').join(' '),
    note: item.list_status === 'off' ? 'deviceDelisted' : item.status === 'offline' ? 'deviceOffline' : '',
  }
}

export const useHostingStore = defineStore('hosting', () => {
  const userStore = useUserStore()
  const applicationRecords = ref<OnboardingItem[]>([])
  const supplierDeviceRecords = ref<SupplierDeviceItem[]>([])
  const verificationRecord = ref<VerificationInfo | null>(null)
  const supplierDashboardRecord = ref<SupplierDashboard | null>(null)
  const supplierWalletRecord = ref<SupplierWallet | null>(null)
  const loading = ref(false)
  const error = ref('')
  const lastUpdated = ref(0)
  const loadedRole = ref<'personal' | 'supplier' | ''>('')
  const loadedUserId = ref<number | null>(null)
  let refreshGeneration = 0

  const currentUserId = computed(() => userStore.userInfo?.id ?? null)
  const dataBelongsToCurrentUser = computed(() => (
    currentUserId.value != null && loadedUserId.value === currentUserId.value
  ))
  const applications = computed(() => dataBelongsToCurrentUser.value ? applicationRecords.value : [])
  const supplierDevices = computed(() => dataBelongsToCurrentUser.value ? supplierDeviceRecords.value : [])
  const verification = computed(() => dataBelongsToCurrentUser.value ? verificationRecord.value : null)
  const supplierDashboard = computed(() => dataBelongsToCurrentUser.value ? supplierDashboardRecord.value : null)
  const supplierWallet = computed(() => dataBelongsToCurrentUser.value ? supplierWalletRecord.value : null)

  const hasMerchantAccess = computed(() => userStore.userInfo?.supplier_status === 'approved')
  const isApprovedMerchant = computed(() => hasMerchantAccess.value && userStore.role === 'supplier')
  const hostingRole = computed(() => {
    if (!userStore.isLogin) return 'viewer'
    if (isApprovedMerchant.value) return 'merchant_operator'
    if (verification.value?.status === 'verified') return 'personal_owner'
    return 'viewer'
  })

  const devices = computed<HostingDeviceItem[]>(() => isApprovedMerchant.value
    ? supplierDevices.value.map(supplierToDevice)
    : applications.value.map(applicationToDevice))

  const statusCounts = computed<Record<HostingDeviceStatus, number>>(() => {
    const result = Object.fromEntries(STATUS_ORDER.map((status) => [status, 0])) as Record<HostingDeviceStatus, number>
    devices.value.forEach((device) => {
      result[device.status] += device.count
    })
    return result
  })

  const totalDeviceCount = computed(() => devices.value.reduce((sum, item) => sum + item.count, 0))
  const runningCount = computed(() => statusCounts.value.running)
  const actionRequiredCount = computed(() => statusCounts.value.action_required)
  const hostingRevenue = computed(() => isApprovedMerchant.value ? supplierWallet.value?.total_revenue ?? null : null)

  function clearRecords() {
    applicationRecords.value = []
    supplierDeviceRecords.value = []
    verificationRecord.value = null
    supplierDashboardRecord.value = null
    supplierWalletRecord.value = null
    lastUpdated.value = 0
  }

  async function refresh() {
    if (loading.value) return
    const generation = refreshGeneration
    loading.value = true
    error.value = ''
    try {
      if (!userStore.userInfo) await userStore.fetchProfile()
      if (generation !== refreshGeneration) return
      const requestUserId = userStore.userInfo?.id ?? null
      const requestRole: 'personal' | 'supplier' = isApprovedMerchant.value ? 'supplier' : 'personal'

      if (loadedUserId.value !== requestUserId || loadedRole.value !== requestRole) {
        clearRecords()
        loadedUserId.value = null
        loadedRole.value = ''
      }

      if (requestRole === 'supplier') {
        const [devicesResult, dashboardResult, walletResult] = await Promise.allSettled([
          getSupplierDevices('all'),
          getDashboard(),
          getSupplierWallet(),
        ])
        if (generation !== refreshGeneration) return
        if (devicesResult.status === 'fulfilled') supplierDeviceRecords.value = devicesResult.value
        if (dashboardResult.status === 'fulfilled') supplierDashboardRecord.value = dashboardResult.value
        if (walletResult.status === 'fulfilled') supplierWalletRecord.value = walletResult.value
        if (devicesResult.status === 'rejected' && dashboardResult.status === 'rejected' && walletResult.status === 'rejected') {
          throw devicesResult.reason
        }
      } else {
        supplierDeviceRecords.value = []
        supplierDashboardRecord.value = null
        supplierWalletRecord.value = null
        const [verificationResult, applicationsResult] = await Promise.allSettled([
          getVerification(),
          getOnboardingMine(),
        ])
        if (generation !== refreshGeneration) return
        if (verificationResult.status === 'fulfilled') verificationRecord.value = verificationResult.value
        if (applicationsResult.status === 'fulfilled') applicationRecords.value = applicationsResult.value
        if (verificationResult.status === 'rejected' && applicationsResult.status === 'rejected') {
          throw applicationsResult.reason
        }
      }
      loadedUserId.value = requestUserId
      loadedRole.value = requestRole
      lastUpdated.value = Date.now()
    } catch (reason) {
      if (generation === refreshGeneration) {
        error.value = reason instanceof Error ? reason.message : 'requestFailed'
      }
    } finally {
      if (generation === refreshGeneration) loading.value = false
    }
  }

  function reset() {
    refreshGeneration += 1
    clearRecords()
    loading.value = false
    error.value = ''
    loadedRole.value = ''
    loadedUserId.value = null
  }

  return {
    applications,
    supplierDevices,
    verification,
    supplierDashboard,
    supplierWallet,
    loading,
    error,
    lastUpdated,
    loadedRole,
    loadedUserId,
    hasMerchantAccess,
    isApprovedMerchant,
    hostingRole,
    devices,
    statusCounts,
    totalDeviceCount,
    runningCount,
    actionRequiredCount,
    hostingRevenue,
    refresh,
    reset,
  }
})
