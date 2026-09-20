import type { Metadata } from "next";
import { LegalDocument, type LegalSection } from "@/components/legal-document";
import { SimplePage } from "@/components/simple-page";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "用戶協議 | KAI星算",
      description: "KAI星算撮合服務、賬號、商家、內容和爭議處理的使用規則。",
    },
    "zh-Hans": {
      title: "用户协议 | KAI星算",
      description: "KAI星算撮合服务、账号、商家、内容和争议处理的使用规则。",
    },
    en: {
      title: "Terms of Service | KAI星算",
      description: "Rules for KAI星算 matching services, accounts, suppliers, content and dispute handling.",
    },
  });
}

const termsSections: LegalSection[] = [
  {
    id: "acceptance",
    title: { zh: "协议主体与接受", en: "Parties and acceptance" },
    paragraphs: [
      {
        zh: "本协议由你与KAI星算运营主体锆芯期算人工智能科技（上海）有限公司共同订立，适用于KAI星算网站、Android 和 iOS 客户端及相关服务。注册、登录、点击同意或继续使用服务，即表示你已阅读并同意本协议及与具体功能相关的有效规则。",
        en: "This agreement is between you and the KAI星算 operator, Zircon Core Futures Computing Artificial Intelligence Technology (Shanghai) Co., Ltd., and applies to the KAI星算 website, Android and iOS apps and related services. By registering, signing in, accepting, or continuing to use the service, you confirm that you have read and agree to this agreement and the effective rules for the feature used.",
      },
      {
        zh: "如你代表企业或其他组织使用服务，你确认已获得充分授权并有权使该主体受本协议约束。未满 18 周岁或不具备相应民事行为能力的人不得注册或使用交易和撮合服务。",
        en: "If you use the service for a company or another organisation, you confirm that you are duly authorised to bind it. Anyone under 18 or without the required civil capacity must not register or use transaction and matching services.",
      },
    ],
  },
  {
    id: "service-scope",
    title: { zh: "服务范围与当前模式", en: "Service scope and current mode" },
    paragraphs: [
      {
        zh: "KAI星算提供自有平台行情、资源目录、需求发布、商家入驻与报价、方案确认、交付协作、历史记录、算力技术社区和客服等功能。当前面向审核的版本采用需求撮合和人工确认模式：用户提交需求后，由商家或平台人员核对资源、价格、交付条件和方案。",
        en: "KAI星算 provides first-party platform market data, resource listings, request publication, supplier onboarding and quotes, plan confirmation, fulfilment collaboration, history, a compute technical community, and support. The current review release uses request matching and manual confirmation: after a request is submitted, a supplier or platform staff verifies resources, price, delivery conditions and the proposed plan.",
      },
      {
        zh: "除另有书面服务文件明确约定，平台展示不等同于资源销售、即时成交或由KAI星算自行提供全部算力。具体服务内容、资源提供方、价格、期限、验收、退款和责任以双方最终确认的订单、方案或合同为准。",
        en: "Unless a separate written service document expressly states otherwise, a platform listing is not a sale, instant transaction or a promise that KAI星算 itself supplies all compute. The final confirmed order, proposal or contract governs the service, provider, price, term, acceptance, refund and responsibility.",
      },
    ],
  },
  {
    id: "account",
    title: { zh: "账号、认证与 KAI 身份", en: "Accounts, verification and KAI identity" },
    items: [
      {
        zh: "你应提交真实、准确、完整且保持更新的注册资料，妥善保管密码、验证码、恢复邮箱和登录设备，并对账号内经合理认证的操作负责。发现异常时应立即修改凭据并联系我们。",
        en: "You must provide accurate, complete and current registration data, safeguard your password, verification codes, recovery email and signed-in devices, and take responsibility for actions reasonably authenticated to your account. If you detect an anomaly, change credentials and contact us promptly.",
      },
      {
        zh: "实名认证、企业认证或商家审核只表示已按当时规则核验已提交材料，不构成对信用、履约能力、资源质量或持续合规的保证。你不得冒用、出借、出租、买卖或批量注册账号。",
        en: "Identity, company or supplier verification means only that submitted materials were reviewed under the rules then in effect; it does not guarantee credit, fulfilment capacity, resource quality or continuing compliance. You must not impersonate another person, lend, rent, sell or mass-register accounts.",
      },
      {
        zh: "KAI 身份为外部统一身份。首次成功的 KAI 登录或注册会仅按 KAI 签发方和主体标识创建一个本地平台账号；不会按 KAI 返回的邮箱、手机号、昵称或头像自动合并既有账号。你可随后自愿设置本地手机号登录标识和密码；未接入短信验证时，该手机号不代表归属核验。找回邮箱仍须通过邮件验证码验证；首次 KAI 账号尚未设置本地密码时，可由近期 KAI 登录授权首次绑定邮箱。解绑或注销KAI星算不会自动注销外部 KAI 账号。你不得向KAI星算提交外部 KAI 密码。",
        en: "KAI identity is an external unified identity. A first successful KAI sign-in or registration creates one local platform account only by KAI issuer and subject; it never automatically merges an existing account using KAI email, mobile number, nickname, or avatar. You may then choose a local mobile sign-in identifier and password; until SMS verification is available, that number does not prove ownership. Recovery email must still be verified by email code; a KAI-first account without a local password may use a recent KAI sign-in to authorise its first email binding. Unlinking or deleting KAI星算 does not automatically delete the external KAI account. Do not submit an external KAI password to KAI星算.",
      },
    ],
  },
  {
    id: "market-data",
    title: { zh: "平台行情与资源展示", en: "Platform market data and listings" },
    paragraphs: [
      {
        zh: "算力报价、K 线、均线、统计和榜单来自平台记录或 KAI Pricing，用于市场观察和撮合参考。数据可能存在延迟、缺口、修正、来源差异或网络故障，不构成投资建议、收益承诺、即时库存、最终报价或必然成交结果。",
        en: "Compute quotes, candlesticks, averages, statistics, and rankings come from platform records or KAI Pricing and are provided for market observation and matching reference. Data may be delayed, incomplete, corrected, differ by source or be affected by network failures. It is not investment advice, a return promise, live inventory, a final quote or a guarantee of a completed transaction.",
      },
      {
        zh: "资源配置、图片和商家描述由相应发布者负责。你应在确认方案前核对 GPU 型号、显存、数量、区域、网络、软件环境、时长、性能口径和验收方法，不得将页面样例视为未经确认的交付承诺。",
        en: "The relevant publisher is responsible for resource configurations, images and supplier descriptions. Before confirming a plan, verify GPU model, memory, quantity, region, network, software environment, duration, performance measurement and acceptance method. Do not treat a page example as an unconfirmed delivery promise.",
      },
    ],
  },
  {
    id: "matching",
    title: { zh: "需求、报价与方案确认", en: "Requests, quotes and plan confirmation" },
    items: [
      {
        zh: "发布需求时，应如实填写用途、型号、数量、时长、区域、预算和联系人，不得发布违法、虚假、重复、侵权或明显无法履行的需求。",
        en: "When publishing a request, truthfully state intended use, model, quantity, duration, region, budget and contact details. Requests must not be unlawful, false, duplicative, infringing or manifestly impossible to fulfil.",
      },
      {
        zh: "商家报价属于待确认方案，只有相关方完成页面或书面确认并明确价格、资源、期限、交付、验收及其他关键条件后，才按确认文件形成相应权利义务。平台状态标签本身不替代必要的合同或确认。",
        en: "A supplier quote is a proposal pending confirmation. Rights and obligations arise under the confirmed document only after the relevant parties confirm the price, resources, term, delivery, acceptance and other key conditions on the platform or in writing. A platform status label does not replace a required contract or confirmation.",
      },
      {
        zh: "提交、报价、反报价和确认可能受到有效期、权限、重复请求控制和风控限制。网络超时或响应不明确时，应先查询现有状态，不得反复提交造成重复业务。",
        en: "Submissions, quotes, counter-offers and confirmations may be subject to validity periods, permissions, duplicate-request controls and risk controls. If a network timeout or ambiguous response occurs, check the existing status before retrying to avoid duplicate business events.",
      },
    ],
  },
  {
    id: "supplier-delivery",
    title: { zh: "商家义务与交付安全", en: "Supplier duties and delivery security" },
    paragraphs: [
      {
        zh: "商家应具备提供所列资源的合法权利和履约能力，保证企业、资源、价格、可用期、地域和交付资料真实有效，及时更新库存与状态，并依法承担服务质量、税务、知识产权和售后责任。不得冒充自营资源或隐瞒关键限制。",
        en: "A supplier must have lawful rights and capacity to provide listed resources, keep company, resource, pricing, availability, region and delivery data accurate, update inventory and status promptly, and bear applicable service-quality, tax, intellectual-property and after-sales duties. A supplier must not impersonate self-operated resources or hide material restrictions.",
      },
      {
        zh: "SSH 或其他交付凭据只能为已确认的合法履约提交，不得提交私钥、与交付无关的生产凭据或未经授权的系统访问。接收方只能在约定范围和期限内使用，不得转交、扫描、提权、攻击或访问无关数据；交付完成后应按约定轮换或撤销凭据。",
        en: "SSH or other delivery credentials may be submitted only for a confirmed lawful fulfilment. Never submit private keys, unrelated production credentials or unauthorised system access. The recipient may use them only within the agreed scope and term and must not transfer, scan, escalate privileges, attack or access unrelated data. Credentials should be rotated or revoked after fulfilment as agreed.",
      },
    ],
  },
  {
    id: "community",
    title: { zh: "算力技术社区与用户内容", en: "Compute technical community and user content" },
    paragraphs: [
      {
        zh: "当前社区仅用于算力产品、站内行情和技术交流，首版仅开放文字动态。你保留对原创内容依法享有的权利，并授予KAI星算在提供、展示、审核、备份和推广相应服务所需范围内的非独占许可。",
        en: "The current community is limited to compute products, first-party platform market updates, and technical discussion, and the initial release supports text posts only. You retain lawful rights in original content and grant KAI星算 a non-exclusive licence limited to providing, displaying, moderating, backing up, and promoting the relevant service.",
      },
      {
        zh: "不得发布违法违规、诈骗、侵权、恶意营销、仇恨骚扰、淫秽暴力、恶意代码，或泄露身份证件、银行卡、密码、SSH 私钥及他人隐私的内容。平台可依法采取限流、隐藏、删除、暂停发布、保全证据或报告等措施，并为误判提供申诉渠道。",
        en: "Do not publish unlawful, fraudulent, infringing, maliciously promotional, hateful, harassing, obscene, violent or malicious-code content, or expose identity documents, bank cards, passwords, SSH private keys or another person's privacy. KAI星算 may lawfully limit reach, hide or remove content, suspend publishing, preserve evidence or report a matter, with an appeal channel for mistakes.",
      },
      {
        zh: "不得利用社区从事新闻采编、新闻转载，或发布公共事务、时政、军事、外交及突发事件的新闻报道或评论。平台保留举报、审核、屏蔽、下架和申诉机制，并可依照适用规则限制或移除超出社区范围的内容。",
        en: "Do not use the community for news gathering or republication, or for reports or commentary about public affairs, politics, military affairs, diplomacy, or emergencies. The platform maintains reporting, moderation, blocking, takedown, and appeal mechanisms and may restrict or remove content outside the community scope.",
      },
    ],
  },
  {
    id: "payments",
    title: { zh: "费用、支付与结算", en: "Fees, payments and settlement" },
    paragraphs: [
      {
        zh: "当前审核版本关闭新的直接交易、充值、提现和在线支付，撮合方案的费用和结算方式应在最终确认文件中明确。页面保留的历史记录或未开放入口不表示相关能力已启用。",
        en: "The current review release disables new direct trading, top-ups, withdrawals and online payments. Fees and settlement for a matched proposal must be stated in the final confirmation. Historical records or an unavailable entry point do not mean that a capability is enabled.",
      },
      {
        zh: "未来如启用平台服务费、支付、提现、返佣或磨损等计费规则，我们会在使用前单独展示适用费率、计算口径、条件、退款和结算规则，并取得必要确认；不会仅凭本协议概括条款自动收取未明确告知的费用。支付结果以服务端验签、查单和账务记录为准。",
        en: "If platform fees, payments, withdrawals, rewards, wear or other charging rules are enabled later, the applicable rate, calculation, conditions, refunds and settlement rules will be shown separately before use and any required confirmation obtained. This general agreement alone does not authorise an undisclosed charge. Payment status is determined by server-side signature verification, order query and ledger records.",
      },
    ],
  },
  {
    id: "prohibited",
    title: { zh: "禁止行为", en: "Prohibited conduct" },
    items: [
      {
        zh: "不得利用服务实施违法计算、网络攻击、恶意扫描、侵入、传播恶意软件、洗钱、诈骗、侵权、绕过监管或其他损害国家安全、公共利益、平台或第三方权益的行为。",
        en: "Do not use the service for unlawful computing, cyberattacks, malicious scanning, intrusion, malware distribution, money laundering, fraud, infringement, regulatory evasion, or conduct harming national security, the public interest, KAI星算 or a third party.",
      },
      {
        zh: "不得破坏接口、爬取非公开数据、绕过访问控制或能力开关、伪造请求来源、干扰行情和交易状态、批量占用资源、操纵评价或帮助他人规避限制。",
        en: "Do not disrupt interfaces, scrape non-public data, bypass access controls or capability flags, forge request origin, interfere with market or transaction state, reserve resources in bulk, manipulate feedback or help another person evade restrictions.",
      },
    ],
  },
  {
    id: "availability-liability",
    title: { zh: "服务变更、可用性与责任", en: "Changes, availability and liability" },
    paragraphs: [
      {
        zh: "我们会合理维护服务，但可能因维护、升级、网络、设备、上游数据、第三方服务、不可抗力或依法处置而中断、延迟或调整。对计划维护会尽量提前提示；紧急安全处置可先采取措施再通知。",
        en: "We use reasonable efforts to maintain the service, but maintenance, upgrades, networks, devices, upstream data, third parties, force majeure or lawful action may cause interruption, delay or adjustment. We aim to give advance notice of planned maintenance; urgent security action may precede notice.",
      },
      {
        zh: "一方因违反协议、故意或过失造成损失，应依法承担相应责任。任何免责或责任限制均不排除法律不得排除的消费者权益、人身损害责任，以及因故意或重大过失造成的责任。对商家与用户之间的独立履约争议，平台将依据记录协助协调，但不因此当然承担资源提供方的全部责任。",
        en: "A party that causes loss through breach, intent or negligence bears responsibility under law. No disclaimer excludes mandatory consumer rights, liability for personal injury, or liability arising from intent or gross negligence. KAI星算 may assist with an independent fulfilment dispute between a supplier and user based on platform records, but does not thereby assume all responsibility of the resource provider.",
      },
    ],
  },
  {
    id: "suspension",
    title: { zh: "暂停、终止与账号注销", en: "Suspension, termination and account deletion" },
    paragraphs: [
      {
        zh: "发生安全风险、违法违规、重大违约、资料虚假、长期未处理异常或主管机关要求时，我们可根据风险采取验证、限制部分功能、暂停或终止服务等必要措施，并在法律允许范围内说明原因和提供申诉。未结履约、账务、争议或法定义务不因账号停用而自动消灭。",
        en: "Where there is a security risk, illegality, material breach, false data, a long-unresolved anomaly or an authority request, we may take necessary measures such as verification, feature restriction, suspension or termination and, where law permits, explain the reason and offer an appeal. Outstanding fulfilment, accounting, disputes and legal obligations do not automatically end when an account is disabled.",
      },
      {
        zh: "你可停止使用或通过账号注销页面申请注销。系统会先提示需要处理的未结事项；注销完成后，账号不能继续登录，可删除资料按隐私政策清理，依法或为未结事项确需保留的记录仅在必要范围内受限保存。注销KAI星算不会注销外部 KAI 账号。",
        en: "You may stop using the service or request deletion on the account-deletion page. The system first identifies outstanding matters. After completion, the account can no longer sign in, deletable data is cleared under the privacy policy, and records required by law or an unresolved matter are retained only as necessary with restricted access. Deleting KAI星算 does not delete the external KAI account.",
      },
    ],
  },
  {
    id: "changes",
    title: { zh: "协议更新", en: "Agreement updates" },
    paragraphs: [
      {
        zh: "因法律、业务或功能变化需要更新时，我们会标明版本与生效日期，并通过页面、站内通知或其他适当方式告知重大变化。依法需要重新同意的，将在继续使用相关功能前取得同意。更新不会追溯减少已经依法产生的权利。",
        en: "If law, business or feature changes require an update, we will identify the version and effective date and notify material changes through the page, an in-app notice or another appropriate method. Where renewed consent is legally required, it will be obtained before continued use of the relevant feature. An update does not retroactively reduce rights already accrued under law.",
      },
    ],
  },
  {
    id: "law-disputes",
    title: { zh: "适用法律、争议与联系", en: "Governing law, disputes and contact" },
    paragraphs: [
      {
        zh: "本协议的订立、履行和解释适用中华人民共和国大陆地区法律。发生争议时，双方应先友好协商；协商不成的，可向运营主体住所地有管辖权的人民法院起诉，但法律对消费者或其他主体的法定管辖另有强制规定的，从其规定。",
        en: "The formation, performance and interpretation of this agreement are governed by the laws of mainland China. The parties should first attempt good-faith negotiation. If no resolution is reached, a claim may be filed with a competent people's court at the operator's domicile, except where mandatory law provides another forum for a consumer or other party.",
      },
      {
        zh: "如对协议、账号、需求、商家、交付或争议处理有疑问，请使用页面底部的唯一公开联系方式联系我们。",
        en: "For questions about this agreement, accounts, requests, suppliers, fulfilment or dispute handling, use the sole public contact method shown below.",
      },
    ],
  },
];

export default function TermsPage() {
  return (
    <SimplePage
      title="用户协议"
      titleEn="Terms of Service"
      description="本协议说明KAI星算当前撮合服务的使用规则、用户与商家责任，以及账号、内容和争议处理安排。"
      descriptionEn="These terms govern KAI星算's current matching service, user and supplier responsibilities, accounts, content and dispute handling."
    >
      <LegalDocument sections={termsSections} accountDeletionLink />
    </SimplePage>
  );
}
