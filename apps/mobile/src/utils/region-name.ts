import { pinyin } from 'pinyin-pro'

const REGION_EN: Record<string, string> = {
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

export function englishRegionName(name: string): string {
  if (!name) return ''
  if (REGION_EN[name]) return REGION_EN[name]

  const directionalZone = name.match(/^(华北|华东|华南|西北|西南)([A-Za-z0-9]+)区$/)
  if (directionalZone) {
    const direction = {
      '华北': 'North China',
      '华东': 'East China',
      '华南': 'South China',
      '西北': 'Northwest China',
      '西南': 'Southwest China',
    }[directionalZone[1]]
    return `${direction} Zone ${directionalZone[2]}`
  }

  const suffix = SUFFIXES.find(([source]) => name.endsWith(source))
  const sourceName = suffix ? name.slice(0, -suffix[0].length) : name
  return `${romanize(sourceName)}${suffix?.[1] || ''}`
}

export function localizeRegionName(name: string, lang: 'zh' | 'en'): string {
  return lang === 'en' ? englishRegionName(name) : name
}
