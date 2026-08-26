<template>
  <view class="page">
    <AppNavBar :title="title" />
    <scroll-view scroll-y class="body">
      <view class="content">
        <text class="h1">{{ title }}</text>
        <text class="date">{{ t('k_fd84f040') }}</text>

        <template v-for="section in document" :key="section.title">
          <text class="h2">{{ section.title }}</text>
          <text v-for="paragraph in section.paragraphs" :key="paragraph" class="p">{{ paragraph }}</text>
        </template>
      </view>
    </scroll-view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import AppNavBar from '@/components/AppNavBar.vue'
import { useI18nStore } from '@/store/i18n'

interface LegalSection {
  title: string
  paragraphs: string[]
}

const AGREEMENT_ZH: LegalSection[] = [
  {
    title: '一、总则',
    paragraphs: [
        'WOD（以下简称“本平台”）提供算力行情参考、已审核 WOD 商家算力使用订单、设备管理和社区交流等功能。用户注册即视为同意本协议全部条款。',
    ],
  },
  {
    title: '二、账户注册与使用',
    paragraphs: [
      '1. 手机号注册目前仅完成图形验证码校验，尚未接入短信验证；手机号只作为当前登录标识，用户不得使用他人号码。',
      '2. 邀请码可用于记录邀请关系；短信验证和真实结算接入前，不发放注册或首单奖励。',
      '3. 用户应妥善保管账户信息，因账户密码泄露导致的损失由用户自行承担。',
      '4. 每个手机号仅可注册一个账户，账户不可转让。',
    ],
  },
  {
    title: '三、算力交易',
    paragraphs: [
      '1. 算力市场分为 KAI 自营和入驻资料已审核商家资源；下架、来源不可用、库存不足或无履约额度的资源不可购买。',
      '2. 算力订单仅按整数小时购买。KAI 自营展示人民币/GPU 小时并换算卡时扣减；商家资源按商家发布的卡时/GPU 小时价格扣减。',
      '3. 订单金额会全额冻结，由 WOD 平台或已审核商家人工交付有效 SSH，用户确认后才创建对应资产。',
      '4. 商家交付 SSH 前可取消订单并退回冻结卡时；SSH 交付后不可自行取消。',
      '5. 平台服务费从商家结算额中计算，不会作为买家额外扣款。',
    ],
  },
  {
    title: '四、卡时与钱包',
    paragraphs: [
      '1. 当前“卡时”仅为平台功能记账单位，不代表现金、存款或可兑付资产。',
      '2. 充值、支付接口、个人及商家提现尚未接入，不会模拟银行到账。',
      '3. 银行卡登记资料仅以掩码展示，并可由用户删除。',
    ],
  },
  {
    title: '五、返佣规则',
    paragraphs: [
      '1. 短信验证、支付及真实结算接入前，不发放注册、邀请、持有或模拟算力收益。',
      '2. 页面中的未结算记录仅供核对，不构成兑付承诺；适用规则以服务页面公布为准。',
    ],
  },
  {
    title: '六、商家规则',
    paragraphs: [
      '1. 用户可申请成为商家，通过后可上架算力设备。',
      '2. 商家须保证设备信息真实有效，及时交付SSH连接信息。',
      '3. 商家可在商家后台管理设备（上架/下架/编辑）、处理订单、查看收益。',
    ],
  },
  {
    title: '七、禁止行为',
    paragraphs: [
      '1. 禁止刷返佣、虚假交易、恶意刷单等行为。',
      '2. 禁止发布违法、侵权、虚假信息。',
      '3. 禁止利用平台进行洗钱、诈骗等违法活动。',
      '4. 违反上述规定的，平台有权冻结账户、扣除违规所得。',
    ],
  },
  {
    title: '八、风险与责任',
    paragraphs: [
      '1. 因网络、设备、系统等不可抗力导致的服务中断，平台不承担责任。',
      '2. 算力价格随市场波动，用户应自行判断风险。',
      '3. 平台不对用户在社区发布的内容真实性负责。',
    ],
  },
  {
    title: '九、联系我们',
    paragraphs: ['如需帮助，请通过平台内客服入口或联系平台服务联络人。'],
  },
]

const AGREEMENT_EN: LegalSection[] = [
  {
    title: '1. General Terms',
    paragraphs: [
        'WOD (the “Platform”) provides market-reference data, usage orders from approved WOD merchants, device management and community features. By registering, you agree to these terms.',
    ],
  },
  {
    title: '2. Account Registration and Use',
    paragraphs: [
      '1. Phone registration currently uses only a visual captcha and does not verify ownership by SMS. The number is only a login identifier; you must not use another person’s number.',
      '2. An invitation code may record a referral relationship. Registration and first-order rewards are not issued until SMS verification and real settlement are connected.',
      '3. You are responsible for safeguarding your account information and for losses caused by disclosure of your account password.',
      '4. Each mobile number may register only one account. Accounts may not be transferred.',
    ],
  },
  {
    title: '3. Compute Transactions',
    paragraphs: [
      '1. The compute market separates KAI Direct resources from offers by merchants with reviewed onboarding materials. Delisted, unavailable, out-of-stock, or unfulfillable resources cannot be purchased.',
      '2. Compute orders use whole hours only. KAI Direct prices are shown in CNY per GPU-hour and converted to CH; merchant offers debit the seller-listed CH per GPU-hour price.',
      '3. The full order amount is frozen. WOD or an approved merchant manually provides valid SSH access, and the matching asset is created only after buyer confirmation.',
      '4. An order may be canceled before SSH delivery and its frozen CH returned. It cannot be self-canceled after SSH delivery.',
      '5. The service fee is calculated from the merchant settlement and is not an additional buyer charge.',
    ],
  },
  {
    title: '4. Compute Hours and Wallet',
    paragraphs: [
      '1. CH is only a Platform ledger unit. It is not cash, a deposit or a redeemable asset.',
      '2. Top-up, payment-provider integration, and personal or merchant withdrawals are not connected; no bank receipt is simulated.',
      '3. Registered bank-card details remain masked and can be deleted by the user.',
    ],
  },
  {
    title: '5. Rebate Rules',
    paragraphs: [
      '1. Registration, invitation, holding and simulated compute rewards are not issued before SMS verification, payments and real settlement are connected.',
      '2. Unsettled records shown on the page are for reconciliation only and do not constitute a payout promise; the rules published on the service page apply.',
    ],
  },
  {
    title: '6. Seller Rules',
    paragraphs: [
      '1. You may apply to become a seller and list compute devices after approval.',
      '2. Sellers must provide accurate, valid device information and deliver SSH connection details promptly.',
      '3. Sellers may use the seller dashboard to manage devices, process orders and review revenue.',
    ],
  },
  {
    title: '7. Prohibited Conduct',
    paragraphs: [
      '1. Rebate manipulation, sham transactions and fraudulent orders are prohibited.',
      '2. Illegal, infringing or false content is prohibited.',
      '3. The Platform may not be used for money laundering, fraud or other illegal activity.',
      '4. The Platform may freeze accounts and recover proceeds obtained through violations of these rules.',
    ],
  },
  {
    title: '8. Risk and Liability',
    paragraphs: [
      '1. The Platform is not liable for service interruptions caused by networks, devices, systems or other events beyond its reasonable control.',
      '2. Compute prices fluctuate with the market. You are responsible for evaluating the associated risks.',
      '3. The Platform is not responsible for the accuracy of content published by users in the community.',
    ],
  },
  {
    title: '9. Contact Us',
    paragraphs: ['For assistance, use the in-app support entry or contact the Platform service liaison.'],
  },
]

const PRIVACY_ZH: LegalSection[] = [
  {
    title: '一、信息收集',
    paragraphs: [
      '本平台收集以下用户信息：',
      '1. 手机号码：仅作为当前注册和登录标识，当前不通过短信验证号码归属。',
      '2. 真实姓名及身份证号：用于实名认证，完成格式校验后提交平台审核。',
      '3. 身份证照片：正反面照片，存储于服务器本地。',
      '4. 银行卡信息：用于经用户授权的银行卡登记与提现审核，采用加密存储并仅返回掩码。',
      '5. 收货地址：省市区及详细地址。',
      '6. 业务交易记录：订单、余额冻结、退款及资金流水。',
    ],
  },
  {
    title: '二、信息使用',
    paragraphs: [
      '1. 用户信息仅用于账户管理、订单处理、身份审核与安全防护。',
      '2. 本平台不会向第三方出售、出租、交换用户个人信息。',
      '3. 身份证照片仅用于核验，不会公开展示。',
      '4. 银行卡信息仅用于用户发起的登记、审核与提现处理；允许删除的卡片可由用户自行删除。',
    ],
  },
  {
    title: '三、信息存储与安全',
    paragraphs: [
      '1. 用户数据存储在平台服务器，采取加密等安全措施。',
      '2. 身份证照片存储在服务器本地目录，仅管理员可访问。',
      '3. 密码采用bcrypt加密存储，不以明文形式保存。',
      '4. 本平台采取合理的安全措施保护用户信息，但不对信息绝对安全做出保证。',
    ],
  },
  {
    title: '四、信息共享',
    paragraphs: [
      '1. 除以下情况外，本平台不会向任何第三方共享用户信息：',
      '• 获得用户明确同意',
      '• 法律法规要求或司法机关要求',
      '• 在相关服务正式开通后，为完成用户明确请求的交易所必需的共享',
      '2. 在共享信息前，本平台会要求接收方承诺保密。',
    ],
  },
  {
    title: '五、用户权利',
    paragraphs: [
      '1. 用户有权查看、修改自己的个人信息。',
      '2. 用户有权删除已绑定的银行卡和地址信息。',
      '3. 如需注销账户或处理个人信息，请联系平台服务联络人提交申请，平台将按适用要求处理。',
    ],
  },
  {
    title: '六、Cookie使用',
    paragraphs: ['本平台使用设备本地存储保存登录令牌（token）和界面设置，不使用跟踪类Cookie。'],
  },
  {
    title: '七、未成年人保护',
    paragraphs: ['本平台仅限18岁以上用户使用，实名认证时会校验年龄。未满18岁的用户无法通过认证。'],
  },
  {
    title: '八、联系方式',
    paragraphs: [
      '如对隐私政策有疑问，请联系：',
        '• 正式客服邮箱与联系方式将在上线前公布',
    ],
  },
]

const PRIVACY_EN: LegalSection[] = [
  {
    title: '1. Information We Collect',
    paragraphs: [
      'The Platform collects the following user information:',
      '1. Mobile number: Used only as the current registration and login identifier; ownership is not currently verified by SMS.',
      '2. Legal name and national ID number: Used for identity verification. After format validation, the information is submitted to the Platform for review.',
      '3. National ID images: Front and back images stored locally on the Platform server.',
      '4. Bank card information: Used for user-authorized registration and withdrawal review, stored encrypted and returned only in masked form.',
      '5. Delivery address: Province, city, district and street address.',
      '6. Business transaction records: Orders, balance freezes, refunds and fund ledger entries.',
    ],
  },
  {
    title: '2. How We Use Information',
    paragraphs: [
      '1. User information is used only for account management, order handling, identity review and security.',
      '2. The Platform does not sell, rent or exchange users’ personal information with third parties.',
      '3. National ID images are used only for verification and are not displayed publicly.',
      '4. Bank-card information is used only for user-initiated registration, review and withdrawal processing; eligible cards can be deleted by the user.',
    ],
  },
  {
    title: '3. Storage and Security',
    paragraphs: [
      '1. User data is stored on Platform servers and protected with encryption and other security measures.',
      '2. National ID images are stored in a local server directory accessible only to administrators.',
      '3. Passwords are stored using bcrypt hashing and are never saved as plain text.',
      '4. The Platform uses reasonable measures to protect user information but cannot guarantee absolute security.',
    ],
  },
  {
    title: '4. Information Sharing',
    paragraphs: [
      '1. The Platform does not share user information with third parties except when:',
      '• You have given explicit consent.',
      '• Sharing is required by law, regulation or a judicial authority.',
      '• After a relevant service opens, sharing is necessary to complete a transaction explicitly requested by you.',
      '2. Before sharing information, the Platform requires the recipient to maintain confidentiality.',
    ],
  },
  {
    title: '5. Your Rights',
    paragraphs: [
      '1. You may view and update your personal information.',
      '2. You may delete linked bank cards and saved addresses.',
      '3. Contact the Platform service liaison to request account closure or personal-information handling. The Platform will process the request in accordance with applicable requirements.',
    ],
  },
  {
    title: '6. Cookies and Local Storage',
    paragraphs: ['The Platform uses local device storage for the login token and interface settings. It does not use tracking cookies.'],
  },
  {
    title: '7. Protection of Minors',
    paragraphs: ['The Platform is available only to users aged 18 or older. Age is checked during identity verification, and users under 18 cannot be verified.'],
  },
  {
    title: '8. Contact Us',
    paragraphs: [
      'For questions about this Privacy Policy, contact:',
        '• The official support email and contact channels will be published before launch.',
    ],
  },
]

const i18n = useI18nStore()
const { t } = i18n
const type = ref<'agreement' | 'privacy'>('agreement')
const title = computed(() => t(type.value === 'privacy' ? '隐私政策' : '用户协议'))
const document = computed(() => {
  const english = i18n.lang === 'en'
  if (type.value === 'privacy') return english ? PRIVACY_EN : PRIVACY_ZH
  return english ? AGREEMENT_EN : AGREEMENT_ZH
})

onLoad((opts) => {
  type.value = opts?.type === 'privacy' ? 'privacy' : 'agreement'
})
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: var(--bg); }
.body { height: 100%; }
.content { padding: 32rpx; padding-bottom: calc(60rpx + var(--safe-bottom)); }
.h1 { display: block; font-size: 36rpx; font-weight: 800; color: var(--text); text-align: center; margin-bottom: 8rpx; }
.date { display: block; font-size: 24rpx; color: var(--text-sub); text-align: center; margin-bottom: 32rpx; }
.h2 { display: block; font-size: 30rpx; font-weight: 700; color: var(--text); margin-top: 32rpx; margin-bottom: 16rpx; }
.p { display: block; font-size: 26rpx; color: var(--text-sub); line-height: 1.8; margin-bottom: 8rpx; }
</style>
