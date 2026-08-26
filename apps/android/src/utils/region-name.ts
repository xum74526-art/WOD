import { pinyin } from 'pinyin-pro'

const REGION_EN: Record<string, string> = {
  '华北': 'North China',
  '华东': 'East China',
  '华中': 'Central China',
  '华南': 'South China',
  '东北': 'Northeast China',
  '西北': 'Northwest China',
  '西南': 'Southwest China',
  '中国大陆': 'Mainland China',
  '亚太': 'Asia Pacific',
  '北美': 'North America',
  '欧洲': 'Europe',
  '中东': 'Middle East',
  '南美': 'South America',
  '非洲': 'Africa',
  '海外': 'Overseas',
  '全球/未披露': 'Global / Undisclosed',
  '全球／未披露': 'Global / Undisclosed',
  '全球 / 未披露': 'Global / Undisclosed',
  '未披露': 'Undisclosed',
  'north_china': 'North China',
  'east_china': 'East China',
  'central_china': 'Central China',
  'south_china': 'South China',
  'northeast_china': 'Northeast China',
  'northwest_china': 'Northwest China',
  'southwest_china': 'Southwest China',
  'china_unspecified': 'Mainland China',
  'asia_pacific': 'Asia Pacific',
  'north_america': 'North America',
  'europe': 'Europe',
  'middle_east': 'Middle East',
  'south_america': 'South America',
  'africa': 'Africa',
  'global_unspecified': 'Global / Undisclosed',
  '北京市': 'Beijing',
  '天津市': 'Tianjin',
  '上海市': 'Shanghai',
  '重庆市': 'Chongqing',
  '河北省': 'Hebei Province',
  '山西省': 'Shanxi Province',
  '辽宁省': 'Liaoning Province',
  '吉林省': 'Jilin Province',
  '黑龙江省': 'Heilongjiang Province',
  '江苏省': 'Jiangsu Province',
  '浙江省': 'Zhejiang Province',
  '安徽省': 'Anhui Province',
  '福建省': 'Fujian Province',
  '江西省': 'Jiangxi Province',
  '山东省': 'Shandong Province',
  '河南省': 'Henan Province',
  '湖北省': 'Hubei Province',
  '湖南省': 'Hunan Province',
  '广东省': 'Guangdong Province',
  '海南省': 'Hainan Province',
  '四川省': 'Sichuan Province',
  '贵州省': 'Guizhou Province',
  '云南省': 'Yunnan Province',
  '陕西省': 'Shaanxi Province',
  '甘肃省': 'Gansu Province',
  '青海省': 'Qinghai Province',
  '台湾省': 'Taiwan',
  '内蒙古自治区': 'Inner Mongolia Autonomous Region',
  '广西壮族自治区': 'Guangxi Zhuang Autonomous Region',
  '西藏自治区': 'Tibet Autonomous Region',
  '宁夏回族自治区': 'Ningxia Hui Autonomous Region',
  '新疆维吾尔自治区': 'Xinjiang Uyghur Autonomous Region',
  '香港特别行政区': 'Hong Kong SAR',
  '澳门特别行政区': 'Macao SAR',
}

// Keep these codes aligned with the canonical backend region mapper. The
// stable code wins when an older product still carries an upstream label.
const MARKET_REGION_EN_BY_CODE: Record<string, string> = {
  north_china: 'North China',
  east_china: 'East China',
  central_china: 'Central China',
  south_china: 'South China',
  northeast_china: 'Northeast China',
  northwest_china: 'Northwest China',
  southwest_china: 'Southwest China',
  china_unspecified: 'Mainland China',
  asia_pacific: 'Asia Pacific',
  north_america: 'North America',
  europe: 'Europe',
  middle_east: 'Middle East',
  south_america: 'South America',
  africa: 'Africa',
  global_unspecified: 'Global / Undisclosed',
}

const MARKET_REGION_TOKEN_EN: Array<[string, string]> = [
  ['中国大陆-东北', 'Northeast China'],
  ['中国大陆-西北', 'Northwest China'],
  ['中国大陆-西南', 'Southwest China'],
  ['中国大陆-华北', 'North China'],
  ['中国大陆-华东', 'East China'],
  ['中国大陆-华中', 'Central China'],
  ['中国大陆-华南', 'South China'],
  ['全球/未披露', 'Global / Undisclosed'],
  ['中国大陆', 'Mainland China'],
  ['亚太', 'Asia Pacific'],
  ['北美', 'North America'],
  ['欧洲', 'Europe'],
  ['中东', 'Middle East'],
  ['南美', 'South America'],
  ['非洲', 'Africa'],
]

const SUFFIXES: Array<[string, string]> = [
  ['特别行政区', ' SAR'],
  ['自治州', ' Autonomous Prefecture'],
  ['自治区', ' Autonomous Region'],
  ['地区', ' Prefecture'],
  ['省', ' Province'],
  ['市', ''],
  ['区', ' District'],
  ['县', ' County'],
  ['旗', ' Banner'],
  ['盟', ' League'],
  ['镇', ' Town'],
]

function romanize(value: string): string {
  const words = pinyin(value, { toneType: 'none', type: 'array' })
  const joined = words.join('').replace(/[^a-zA-Z0-9]/g, '')
  return joined ? joined.charAt(0).toUpperCase() + joined.slice(1) : value
}

export function englishRegionName(name: string, regionCode = ''): string {
  if (!name) return ''
  const mappedByCode = MARKET_REGION_EN_BY_CODE[String(regionCode || '').trim().toLowerCase()]
  if (mappedByCode) return mappedByCode
  const compactName = name.replace(/\s+/g, '').replace(/／/g, '/')
  if (REGION_EN[name]) return REGION_EN[name]
  if (REGION_EN[compactName]) return REGION_EN[compactName]

  const marketToken = MARKET_REGION_TOKEN_EN.find(([source]) => compactName.includes(source))
  if (marketToken) return marketToken[1]

  // KAI identifiers such as EU-West and CN-East-1 are already readable.
  if (!/[\u3400-\u9fff]/.test(name)) return name

  const directionalZone = name.match(/^(华北|华东|华中|华南|东北|西北|西南)([A-Za-z0-9]+)区$/)
  if (directionalZone) {
    const direction = {
      '华北': 'North China',
      '华东': 'East China',
      '华中': 'Central China',
      '华南': 'South China',
      '东北': 'Northeast China',
      '西北': 'Northwest China',
      '西南': 'Southwest China',
    }[directionalZone[1]]
    return `${direction} Zone ${directionalZone[2]}`
  }

  const suffix = SUFFIXES.find(([source]) => name.endsWith(source))
  const sourceName = suffix ? name.slice(0, -suffix[0].length) : name
  return `${romanize(sourceName)}${suffix?.[1] || ''}`
}

export function localizeRegionName(name: string, lang: 'zh' | 'en', regionCode = ''): string {
  return lang === 'en' ? englishRegionName(name, regionCode) : name
}

export function localizeMarketLocation(
  regionName: string | null | undefined,
  regionCode: string | null | undefined,
  detail: string | null | undefined,
  lang: 'zh' | 'en',
): string {
  const rawRegion = String(regionName || '').trim()
  const rawDetail = String(detail || '').trim()
  const region = localizeRegionName(rawRegion, lang, String(regionCode || ''))
  if (!rawDetail || rawDetail === '-' || rawDetail === rawRegion) return region || rawDetail

  const localizedDetail = localizeRegionName(rawDetail, lang)
  const comparable = (value: string) => value.toLowerCase().replace(/[\s·\/_／-]+/g, '')
  if (!localizedDetail || comparable(localizedDetail) === comparable(region)) return region
  return [region, localizedDetail].filter(Boolean).join(' · ')
}
