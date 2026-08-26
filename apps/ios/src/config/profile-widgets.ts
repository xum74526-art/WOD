export type ProfileRole = 'personal' | 'supplier'

export interface ProfileWidget {
  key: string
  label: string
  icon: string
  route: string
}

export interface ProfileWidgetGroup {
  key: string
  label: string
  items: ProfileWidget[]
}

const PERSONAL_SERVICE_ITEMS: ProfileWidget[] = [
  { key: 'orders', label: '我的订单', icon: 'order', route: '/pages/orders/index' },
  { key: 'device', label: '设备状态', icon: 'device', route: '/pages/devices/index' },
  { key: 'wallet', label: '钱包', icon: 'coin', route: '/pages/wallet/index' },
  { key: 'revenue', label: '收益中心', icon: 'revenue', route: '/pages/revenue/index' },
  { key: 'rebate', label: 'rebateCenter', icon: 'refresh', route: '/pages/rebate/index' },
  { key: 'procurement', label: 'buyRequests', icon: 'search', route: '/pages/buy-request/index' },
]

const MERCHANT_APPLICATION_ITEM: ProfileWidget = {
  key: 'merchant-join',
  label: 'merchantJoin',
  icon: 'gpu',
  route: '/pages/supplier/apply',
}

const PERSONAL_ACCOUNT_ITEMS: ProfileWidget[] = [
  { key: 'bank', label: '银行卡', icon: 'bank-card', route: '/pages/bank-cards/index' },
  { key: 'verified', label: '实名认证', icon: 'verified', route: '/pages/verification/index' },
  { key: 'coupon', label: '优惠券', icon: 'coupon', route: '/pages/coupons/index' },
  { key: 'address', label: '地址管理', icon: 'address', route: '/pages/addresses/index' },
  { key: 'settings', label: '设置', icon: 'settings', route: '/pages/settings/index' },
  { key: 'online', label: '在线客服', icon: 'online-service', route: '/pages/kefu/index' },
]

const SUPPLIER_OPERATION_ITEMS: ProfileWidget[] = [
  { key: 'orders', label: 'merchantOrders', icon: 'order', route: '/pages/supplier/orders' },
  { key: 'overview', label: 'merchantOverview', icon: 'gpu', route: '/pages/supplier/dashboard' },
  { key: 'revenue', label: 'revenueSettle', icon: 'revenue', route: '/pages/supplier/revenue' },
  { key: 'rebate', label: 'rebateSummary', icon: 'refresh', route: '/pages/supplier/rebate' },
  { key: 'stats', label: 'dataOps', icon: 'filter', route: '/pages/supplier/stats' },
  { key: 'assets', label: 'assetManage', icon: 'device', route: '/pages/supplier/devices' },
  { key: 'merchant-settings', label: 'merchantSettings', icon: 'settings', route: '/pages/supplier/settings' },
]

const SUPPLIER_ACCOUNT_ITEMS: ProfileWidget[] = [
  { key: 'wallet', label: 'wallet', icon: 'coin', route: '/pages/wallet/index' },
  { key: 'bank', label: 'bankCard', icon: 'bank-card', route: '/pages/bank-cards/index' },
  { key: 'verified', label: '实名认证', icon: 'verified', route: '/pages/verification/index' },
  { key: 'coupon', label: 'coupons', icon: 'coupon', route: '/pages/coupons/index' },
  { key: 'address', label: 'addressManage', icon: 'address', route: '/pages/addresses/index' },
  { key: 'procurement', label: 'buyRequests', icon: 'search', route: '/pages/buy-request/index' },
  { key: 'account-settings', label: 'accountSettings', icon: 'user', route: '/pages/settings/index' },
  { key: 'online', label: '在线客服', icon: 'online-service', route: '/pages/kefu/index' },
]

export function getProfileWidgetGroups(
  role: ProfileRole,
  hasSupplierAccess: boolean,
): ProfileWidgetGroup[] {
  if (role === 'supplier') {
    return [
      { key: 'merchant-operations', label: 'merchantOperations', items: [...SUPPLIER_OPERATION_ITEMS] },
      { key: 'account-tools', label: 'accountTools', items: [...SUPPLIER_ACCOUNT_ITEMS] },
    ]
  }

  return [
    { key: 'personal-services', label: 'personalServices', items: hasSupplierAccess ? [...PERSONAL_SERVICE_ITEMS] : [...PERSONAL_SERVICE_ITEMS, MERCHANT_APPLICATION_ITEM] },
    { key: 'account-tools', label: 'accountTools', items: [...PERSONAL_ACCOUNT_ITEMS] },
  ]
}
