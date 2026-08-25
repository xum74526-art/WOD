export type HomePromotionNavigation = 'navigateTo' | 'switchTab'

export interface HomePromotionItem {
  id: 'market' | 'hourly' | 'wallet'
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
  id: 'market' | 'hourly' | 'wallet'
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
    image: '/static/gpu/RTX5090.jpg',
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
    image: '/static/gpu/H100.jpg',
    route: '/pages/quote/index',
    navigation: 'navigateTo',
  },
  {
    id: 'wallet',
    kickerKey: 'homePromoWalletKicker',
    titleKey: 'homePromoWalletTitle',
    descriptionKey: 'homePromoWalletDescription',
    actionKey: 'homePromoWalletAction',
    imageAltKey: 'homePromoWalletImageAlt',
    image: '/static/gpu/RTX4090.jpg',
    route: '/pages/wallet/index',
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
    id: 'wallet',
    textKey: 'homeNoticeWallet',
    route: '/pages/wallet/index',
    navigation: 'navigateTo',
  },
]
