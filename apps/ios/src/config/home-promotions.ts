export type HomePromotionNavigation = 'navigateTo' | 'switchTab'

export interface HomePromotionItem {
  id: 'market' | 'hourly' | 'request'
  kickerKey: string
  titleKey: string
  descriptionKey: string
  actionKey: string
  imageAltKey: string
  image: string
  route: string
  navigation: HomePromotionNavigation
}

export interface HomeNoticeItem {
  id: 'market' | 'hourly' | 'request'
  textKey: string
  route: string
  navigation: HomePromotionNavigation
}

export const HOME_PROMOTIONS: readonly HomePromotionItem[] = [
  {
    id: 'hourly',
    kickerKey: 'homePromoHourlyKicker',
    titleKey: 'homePromoHourlyTitle',
    descriptionKey: 'homePromoHourlyDescription',
    actionKey: 'homePromoHourlyAction',
    imageAltKey: 'homePromoHourlyImageAlt',
    image: '/static/products/gpu.png',
    route: '/pages/market/index',
    navigation: 'switchTab',
  },
  {
    id: 'market',
    kickerKey: 'homePromoMarketKicker',
    titleKey: 'homePromoMarketTitle',
    descriptionKey: 'homePromoMarketDescription',
    actionKey: 'homePromoMarketAction',
    imageAltKey: 'homePromoMarketImageAlt',
    image: '/static/products/gpu.png',
    route: '/pages/quote/index',
    navigation: 'navigateTo',
  },
  {
    id: 'request',
    kickerKey: 'homePromoRequestKicker',
    titleKey: 'homePromoRequestTitle',
    descriptionKey: 'homePromoRequestDescription',
    actionKey: 'homePromoRequestAction',
    imageAltKey: 'homePromoRequestImageAlt',
    image: '/static/products/gpu.png',
    route: '/pages/buy-request/index?compose=1',
    navigation: 'navigateTo',
  },
]

export const HOME_NOTICES: readonly HomeNoticeItem[] = [
  {
    id: 'hourly',
    textKey: 'homeNoticeHourly',
    route: '/pages/market/index',
    navigation: 'switchTab',
  },
  {
    id: 'market',
    textKey: 'homeNoticeMarket',
    route: '/pages/quote/index',
    navigation: 'navigateTo',
  },
  {
    id: 'request',
    textKey: 'homeNoticeRequest',
    route: '/pages/buy-request/index?compose=1',
    navigation: 'navigateTo',
  },
]
