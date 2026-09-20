import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  getLegalDocument,
  LEGAL_ADDRESS,
  LEGAL_CONTACT_PHONE,
  LEGAL_EFFECTIVE_AT,
  LEGAL_ICP_FILING,
  LEGAL_OPERATOR,
  LEGAL_UPDATED_AT,
  LEGAL_VERSION,
  type LegalDocument,
} from '../src/config/legal-documents.ts'

function textOf(document: LegalDocument): string {
  return [
    document.title,
    ...document.metadata.flatMap((item) => [item.label, item.value]),
    ...document.introduction,
    ...document.sections.flatMap((section) => [section.title, ...section.paragraphs]),
  ].join('\n')
}

test('legal metadata identifies the operator, version, dates, filing and only approved phone', () => {
  assert.equal(LEGAL_VERSION, '1.3')
  assert.equal(LEGAL_UPDATED_AT, '2026-09-20')
  assert.equal(LEGAL_EFFECTIVE_AT, '2026-09-20')
  assert.equal(LEGAL_OPERATOR, '锆芯期算人工智能科技（上海）有限公司')
  assert.equal(LEGAL_ADDRESS, '上海市浦东新区川南奉公路5058号3幢一层（集中登记地）')
  assert.equal(LEGAL_ICP_FILING, '沪ICP备2026046279号-1')
  assert.equal(LEGAL_CONTACT_PHONE, '+86 4001082026')

  for (const kind of ['agreement', 'privacy'] as const) {
    const document = getLegalDocument(kind, 'zh-Hans')
    const source = textOf(document)
    assert.match(source, /锆芯期算人工智能科技（上海）有限公司/)
    assert.match(source, /沪ICP备2026046279号-1/)
    assert.equal((source.match(/\+86 4001082026/g) || []).length, 1)
    assert.doesNotMatch(source, /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i)
    assert.doesNotMatch(source, /将在上线前公布|待补充|TODO|TBD/i)
  }
})

test('privacy policy covers actual data, permissions, processors, retention and user rights', () => {
  const privacy = textOf(getLegalDocument('privacy', 'zh-Hans'))
  for (const requirement of [
    /找回邮箱/,
    /KAI 身份/,
    /KAI.*邮箱、姓名和头像/,
    /Tesseract OCR/,
    /银行卡/,
    /SSH/,
    /com\.kai\.ztwstarmap/,
    /READ_MEDIA_VISUAL_USER_SELECTED/,
    /均不为当前功能申请麦克风权限/,
    /DCloud App 引擎 \/ uni-app/,
    /3\.0\.0-5020420260813003/,
    /Android ID/,
    /OAID/,
    /剪贴板/,
    /不读取 IMEI、IMSI/,
    /阿里云中国香港区域/,
    /cn-hongkong/,
    /所有地区的用户使用业务联网功能/,
    /独立且默认不勾选的选项取得单独同意/,
    /不用于广告、用户画像或个性化推荐/,
    /文字、图片或视频/,
    /网易 163 邮箱服务/,
    /广州网易计算机系统有限公司/,
    /auth\.kai\.com\/privacy/,
    /dcloud\.io\/license\/appprivacy\.html/,
    /三十分钟/,
    /二十四小时/,
    /最长保留七天/,
    /通常保存六个月/,
    /【敏感个人信息】/,
    /依法取得单独同意/,
    /隐私选择.*撤回并返回/,
    /账号注销/,
    /年满十八周岁/,
  ]) assert.match(privacy, requirement)
  assert.doesNotMatch(privacy, /个人信息原则上存储在中华人民共和国境内|Data is generally stored on servers in mainland China/)
  assert.doesNotMatch(privacy, /实际范围以后续正式安装包检测结果|可能涉及的 OAID|七相支付|Qixiang Pay/)
  assert.ok(getLegalDocument('privacy', 'zh-Hans').sections.length >= 9)
})

test('agreement reflects matchmaking by default and gates future direct trading', () => {
  const matchmaking = textOf(getLegalDocument('agreement', 'zh-Hans'))
  assert.match(matchmaking, /当前审核版默认采用撮合模式/)
  assert.match(matchmaking, /不开放新充值、新提现或在线收取交易款项/)
  assert.match(matchmaking, /行情.*不构成投资建议、即时库存、固定报价、成交承诺或收益保证/)
  assert.match(matchmaking, /SSH 主机、端口、用户名和凭据/)
  assert.match(matchmaking, /费用、返佣与展示信息/)
  assert.match(matchmaking, /运营主体住所地有管辖权的人民法院/)
  assert.match(matchmaking, /未来直接交易仅会/)
  assert.match(matchmaking, /启用时将升级适用协议版本/)
  assert.match(matchmaking, /客户端页面或跳转结果本身不构成入账凭证/)
})

test('Traditional Chinese is the default-ready presentation and English is complete', () => {
  const traditional = getLegalDocument('privacy', 'zh-Hant')
  const traditionalText = textOf(traditional)
  assert.equal(traditional.title, '隱私政策')
  assert.match(traditionalText, /聯繫我們：\+86 4001082026/)
  assert.match(traditionalText, /賬號註銷/)
  for (const legalValue of [LEGAL_OPERATOR, LEGAL_ADDRESS, LEGAL_ICP_FILING]) assert.equal(traditionalText.includes(legalValue), true)
  assert.doesNotMatch(traditionalText, /鋯芯|浦東新區|滬ICP備/)

  const englishPrivacy = textOf(getLegalDocument('privacy', 'en'))
  const englishAgreement = textOf(getLegalDocument('agreement', 'en'))
  assert.match(englishPrivacy, /Privacy Policy/)
  assert.match(englishPrivacy, /DCloud App Engine \/ uni-app/)
  assert.match(englishPrivacy, /auth\.kai\.com/)
  assert.match(englishPrivacy, /separate unchecked choice/)
  assert.match(englishPrivacy, /Contact us: \+86 4001082026/)
  assert.match(englishAgreement, /User Agreement/)
  assert.match(englishAgreement, /Current matchmaking mode and conditional direct trading/)
  assert.match(englishAgreement, /laws of the People’s Republic of China/)
})

test('the legal page renders document metadata and settings exposes both entries', () => {
  const page = readFileSync(new URL('../src/pages/agreement/index.vue', import.meta.url), 'utf8')
  const settings = readFileSync(new URL('../src/pages/settings/index.vue', import.meta.url), 'utf8')
  assert.match(page, /getLegalDocument\(kind\.value, i18n\.lang\)/)
  assert.doesNotMatch(page, /directTradeEnabled|useCommerceStore/)
  assert.match(page, /v-for="item in document.metadata"/)
  assert.match(page, /v-for="section in document.sections"/)
  assert.match(page, /isSensitiveParagraph/)
  assert.match(settings, /nav\('\/pages\/agreement\/index\?type=agreement'\)/)
  assert.match(settings, /nav\('\/pages\/agreement\/index\?type=privacy'\)/)
})

test('Android native privacy dialog links to the fixed Simplified Chinese review policy', () => {
  const nativePrivacy = readFileSync(new URL('../src/androidPrivacy.json', import.meta.url), 'utf8')
  assert.match(nativePrivacy, /https:\/\/wod\.kai\.com\/privacy\/zh-cn/)
  assert.match(nativePrivacy, /版本 1\.3，2026-09-20/)
  assert.match(nativePrivacy, /锆芯期算人工智能科技（上海）有限公司/)
  assert.doesNotMatch(nativePrivacy, /https:\/\/wod\.kai\.com\/privacy\\"/)
})
