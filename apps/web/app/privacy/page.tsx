import type { Metadata } from "next";
import { LegalDocument, type LegalSection } from "@/components/legal-document";
import { SimplePage } from "@/components/simple-page";
import { localizedPageMetadata } from "@/lib/server/localized-metadata";

export function generateMetadata(): Promise<Metadata> {
  return localizedPageMetadata({
    "zh-Hant": {
      title: "隱私政策 | ZTW",
      description: "了解 ZTW 如何處理和保護個人信息，以及如何行使個人信息權利。",
    },
    "zh-Hans": {
      title: "隐私政策 | ZTW",
      description: "了解 ZTW 如何处理和保护个人信息，以及如何行使个人信息权利。",
    },
    en: {
      title: "Privacy Policy | ZTW",
      description: "How ZTW processes and protects personal information and how to exercise privacy rights.",
    },
  });
}

const privacySections: LegalSection[] = [
  {
    id: "scope",
    title: { zh: "适用范围与个人信息处理者", en: "Scope and data controller" },
    paragraphs: [
      {
        zh: "本政策适用于 ZTW 网站、Android 与 iOS 客户端以及与账号、算力行情、需求撮合、商家协作、社区资讯和客服相关的服务。个人信息处理者为锆芯期算人工智能科技（上海）有限公司。",
        en: "This policy applies to the ZTW website, Android and iOS apps, and related account, compute-market, request-matching, supplier, community and support services. The data controller is Zircon Core Futures Computing Artificial Intelligence Technology (Shanghai) Co., Ltd.",
      },
      {
        zh: "我们遵循合法、正当、必要和诚信原则，仅为本政策列明的目的处理所需信息。不同功能实际处理的信息取决于你是否启用和使用该功能。",
        en: "We process only the information needed for the purposes stated here, following the principles of lawfulness, fairness, necessity and good faith. The information actually processed depends on the features you choose to use.",
      },
    ],
  },
  {
    id: "information",
    title: { zh: "我们处理的信息", en: "Information we process" },
    items: [
      {
        zh: "账号与登录：手机号码、用户名或昵称、加密后的密码、登录会话和账号状态。密码以不可逆摘要方式保存，不保存明文密码。",
        en: "Account and sign-in: mobile number, username or nickname, password hash, sign-in session and account status. Passwords are stored as non-reversible hashes, never as plaintext.",
      },
      {
        zh: "邮箱找回：你主动绑定的找回邮箱、验证码发送与校验状态、短时验证票据和重置票据。邮箱仅用于账号找回和必要安全通知。",
        en: "Email recovery: the recovery email you bind, verification delivery and validation state, and short-lived verification and reset tickets. The email is used only for account recovery and necessary security notices.",
      },
      {
        zh: "KAI 身份关联：你主动发起关联时，由关联身份服务返回的主体标识、关联结果和一次性短时票据；我们不会索取或保存你的外部 KAI 密码。",
        en: "KAI identity linking: when you initiate linking, we process the subject identifier, linking result and one-time short-lived ticket returned by the linked identity service. We do not request or store your external KAI password.",
      },
      {
        zh: "实名核验：姓名、身份证件号码、证件正反面图像、核验结果和审核状态。当前文字识别由平台自管环境中的本地 OCR（Tesseract）完成，不向第三方 OCR 服务传送证件图像。",
        en: "Identity verification: legal name, identity-document number, front and back images, verification result and review status. Text recognition currently runs through local OCR (Tesseract) in an environment controlled by the platform; document images are not sent to a third-party OCR service.",
      },
      {
        zh: "履约与结算资料：在对应功能可用且由你提交时，处理收货或服务地址、银行卡号及持卡信息、企业和开票资料；页面展示时会尽量脱敏。",
        en: "Fulfilment and settlement data: when the relevant feature is available and you submit it, we process delivery or service addresses, bank-card and cardholder information, and company or invoicing data. Displayed values are masked where practicable.",
      },
      {
        zh: "需求与商家协作：联系人、联系电话、GPU 或服务器型号、数量、时长、区域、配置和其他需求；商家资料、资源配置、报价、库存确认和交付记录。",
        en: "Requests and supplier collaboration: contact name and number, GPU or server model, quantity, duration, region, configuration and other requirements; supplier details, resource configuration, quotes, availability confirmation and delivery records.",
      },
      {
        zh: "交付凭据：商家为已确认交付主动提交的 SSH 主机、端口、用户名、公钥或其他必要凭据。此类信息仅供授权履约、排障和争议核验，并按敏感信息采取访问控制。",
        en: "Delivery credentials: SSH host, port, username, public key or other necessary credentials submitted by a supplier for a confirmed delivery. These are restricted to authorised fulfilment, troubleshooting and dispute review and are access-controlled as sensitive data.",
      },
      {
        zh: "业务记录：需求、报价、订单、资产、钱包与账务记录、结算、返佣、退款、投诉、争议及相关操作记录。未向当前版本开放的直接交易能力不会仅因代码保留而收集额外信息。",
        en: "Business records: requests, quotes, orders, assets, wallet and ledger entries, settlements, rewards, refunds, complaints, disputes and related actions. Direct-trade capabilities not available in the current release do not collect additional data merely because supporting code remains.",
      },
      {
        zh: "社区与客服：你发布的帖子、评论、图片或视频、点赞关注等互动，以及客服对话、工单内容和处理状态。公开发布的内容会向其他用户展示。",
        en: "Community and support: posts, comments, images or videos, likes, follows and other interactions, plus support conversations, ticket content and status. Content you publish publicly is visible to other users.",
      },
      {
        zh: "设备与日志：设备品牌和型号、操作系统和 App 版本、IP 地址、User-Agent、网络类型、请求时间、错误与安全日志，以及打包组件在必要场景可能涉及的 OAID，用于运行兼容、安全、风控、排障和故障分析，不用于本项目的广告或个性化推荐。",
        en: "Device and log data: device brand and model, operating system and app version, IP address, User-Agent, network type, request time, error and security logs, and OAID that packaged components may involve where necessary. These are limited to runtime compatibility, security, risk control, troubleshooting and fault analysis, not advertising or personalised recommendations in this product.",
      },
    ],
  },
  {
    id: "source-purpose",
    title: { zh: "信息来源、处理目的与依据", en: "Sources, purposes and legal bases" },
    paragraphs: [
      {
        zh: "信息主要来自你的主动提交、你在服务中的操作、已登录设备自动生成的必要日志、商家或交易相对方为履约提交的资料，以及你明确授权的 KAI 身份关联。我们将其用于注册登录、账号安全与找回、身份核验、撮合和履约、结算与争议处理、内容展示、客服、风控、故障诊断及遵守法律义务。",
        en: "Information comes mainly from your submissions and actions, necessary logs generated by signed-in devices, fulfilment data supplied by a supplier or counterparty, and KAI identity linking that you expressly authorise. We use it for registration and sign-in, account security and recovery, identity verification, matching and fulfilment, settlement and disputes, content display, support, risk control, troubleshooting and legal compliance.",
      },
      {
        zh: "我们根据履行与你之间的协议、取得你的同意或单独同意、履行法定义务及保障系统安全处理信息。涉及身份证件、银行卡等敏感个人信息时，仅在具有特定目的和充分必要性时处理，并在对应功能中依法取得单独同意和提供更严格保护。SSH 等精确交付凭据按高敏业务秘密实施加密、最小权限和访问审计，但不在尚未实现单独同意的流程中宣称已取得该同意。",
        en: "We rely on performance of our agreement with you, your consent or separate consent, legal obligations, and system-security needs. Sensitive personal information such as identity documents and bank-card data is processed only for a specific and necessary purpose, with legally required separate consent in the relevant feature and enhanced protection. Precise SSH and other delivery credentials are protected as high-risk business secrets through encryption, least privilege and access auditing; we do not claim separate consent where that workflow is not implemented.",
      },
    ],
  },
  {
    id: "permissions",
    title: { zh: "设备权限", en: "Device permissions" },
    items: [
      {
        zh: "网络权限用于登录、获取行情、提交需求、加载资讯和同步业务状态，是联网服务的必要权限。",
        en: "Network access is required to sign in, obtain market data, submit requests, load news and synchronise service status.",
      },
      {
        zh: "相机、相册、图片或视频访问仅在你主动拍摄、选择头像、上传证件或发布媒体内容时请求；麦克风仅在你主动录制含声音的视频时使用。拒绝后仅相应上传或录制功能不可用。",
        en: "Camera, photo-library, image or video access is requested only when you take a photo, choose an avatar, upload a document or publish media. Microphone access is used only when you record a video with sound. Refusal affects only the relevant upload or recording feature.",
      },
      {
        zh: "ZTW 当前不以提供核心服务为由申请通讯录或精确位置权限。你可在系统设置中关闭已授予权限。",
        en: "ZTW does not request contacts or precise location as a condition of its core service. You can revoke granted permissions in system settings.",
      },
    ],
  },
  {
    id: "processors",
    title: { zh: "受托处理与第三方服务", en: "Processors and third-party services" },
    paragraphs: [
      {
        zh: "为提供相应功能，我们仅在必要范围内向受合同与安全约束的服务提供方传输数据，并要求其不得用于约定目的以外的用途。实际启用情况以你使用的功能、当前安装包和实际 SDK 检测结果为准。",
        en: "To provide the relevant feature, we transmit data only as necessary to service providers subject to contractual and security restrictions and prohibit use beyond the agreed purpose. Actual activation depends on the feature used, the installed package and the verified SDK inventory.",
      },
    ],
    items: [
      {
        zh: "阿里云中国香港区域（cn-hongkong）：作为云基础设施受托方，为核心 API、数据库、上传文件、备份与安全防护提供计算和存储能力，可能处理本政策列明的账号、实名、业务、内容及日志信息。服务区域位于中国香港特别行政区。",
        en: "Alibaba Cloud Hong Kong region (cn-hongkong): as the contracted cloud-infrastructure provider, it supplies compute, storage, backup and security capabilities for the core API, database and uploaded files, and may process the account, identity, business, content and log data described in this Policy. The service region is Hong Kong SAR.",
      },
      {
        zh: "DCloud uni-app 基础运行框架（开发者：数字天堂（北京）网络技术有限公司）：在你同意本政策后提供 App 运行、渲染、网络、媒体播放、兼容与故障分析能力，可能处理设备品牌和型号、操作系统、应用版本、网络类型、IP 地址、User-Agent、运行日志，以及打包组件可能涉及的 OAID；不用于本项目广告或个性化推荐。后续披露将以实际安装包检测结果和 SDK 清单为准。",
        en: "DCloud uni-app base runtime (developer: Digital Paradise (Beijing) Network Technology Co., Ltd.): after you consent to this policy, it provides app runtime, rendering, networking, media playback, compatibility and fault analysis. It may process device brand and model, operating system, app version, network type, IP address, User-Agent and runtime logs, and packaged components may involve OAID. It is not used for advertising or personalised recommendations in this product. Future disclosure will follow verified package scans and the SDK inventory.",
      },
      {
        zh: "KAI 关联身份服务：仅在你主动选择 KAI 身份登录或绑定时处理主体标识、授权状态和一次性票据，不接收外部账号密码。",
        en: "KAI linked-identity service: processes the subject identifier, authorisation state and one-time ticket only when you choose KAI sign-in or linking, and does not provide us with the external account password.",
      },
      {
        zh: "哔哩哔哩视频服务：当你打开来源为哔哩哔哩的资讯视频时，播放请求会向其服务发送视频标识、IP 地址、浏览器或设备请求信息；其处理同时受其隐私规则约束。",
        en: "Bilibili video service: when you open a news video sourced from Bilibili, the playback request sends the video identifier, IP address, and browser or device request data to its service. Its own privacy rules also apply.",
      },
      {
        zh: "网易 163 邮件服务：仅为发送邮箱验证码、找回链接或必要安全通知处理收件邮箱、邮件内容及投递状态；我们不会在公开页面披露内部发信账号或授权凭据。",
        en: "NetEase 163 Mail: processes the recipient email, message content and delivery status only to send verification codes, recovery links or necessary security notices. We do not disclose internal sender accounts or credentials on public pages.",
      },
      {
        zh: "条件启用的支付服务：当前审核版本关闭新直接交易和支付。若未来启用七相支付（Qixiang Pay）或其他支付机构，我们会在功能启用前另行告知服务方、处理信息、手续费和规则，并依法取得所需同意。",
        en: "Conditionally enabled payment services: new direct trading and payments are disabled in the current review release. If Qixiang Pay or another payment provider is enabled later, we will first disclose the provider, information processed, fees and rules and obtain any legally required consent.",
      },
    ],
  },
  {
    id: "sharing",
    title: { zh: "共享、转让与公开披露", en: "Sharing, transfer and public disclosure" },
    paragraphs: [
      {
        zh: "我们不出售个人信息。除受托服务、按你的指示向需求方或商家提供履约所需资料、公司依法发生合并重组并继续受本政策约束、履行法定义务或应主管机关要求外，我们不会向其他主体提供个人信息。",
        en: "We do not sell personal information. We do not provide it to another party except for contracted services, fulfilment information shared with a requester or supplier at your direction, a lawful merger or reorganisation subject to continued protection, legal obligations, or a competent authority's lawful request.",
      },
      {
        zh: "帖子、评论、昵称、头像及你选择公开的商家或资源信息会在相应页面公开。请勿在公开内容中发布身份证件、银行卡、密码、SSH 私钥等敏感资料。",
        en: "Posts, comments, nickname, avatar, and supplier or resource information you choose to publish are public on the relevant pages. Do not publish identity documents, bank cards, passwords, SSH private keys or other sensitive data.",
      },
    ],
  },
  {
    id: "cross-border",
    title: { zh: "存储地点与跨境处理", en: "Storage location and cross-border processing" },
    paragraphs: [
      {
        zh: "当前 ZTW 核心 API、数据库及上传文件部署在阿里云中国香港区域（cn-hongkong）。当中国大陆用户使用服务时，本政策列明的账号、找回邮箱、KAI 关联、实名与银行卡、地址、撮合交易与 SSH 交付、社区客服、设备网络及日志信息，会通过加密传输发送至中国香港特别行政区并在那里存储和处理，用于提供服务、履约、安全防护、故障处理及依法保存。",
        en: "ZTW's core API, database and uploaded files are currently deployed in Alibaba Cloud's Hong Kong region (cn-hongkong). When a user in mainland China uses the service, the account, recovery-email, KAI-link, identity and bank-card, address, matchmaking and SSH-delivery, community and support, device/network and log data described in this Policy is encrypted in transit to Hong Kong SAR and stored and processed there for service delivery, fulfilment, security, troubleshooting and legally required retention.",
      },
      {
        zh: "该中国香港服务环境由本政策所列运营主体控制，云基础设施服务商为阿里云；处理目的、方式和信息种类限于本政策所列范围。你可通过账号功能或“联系我们：+86 4001082026”向运营主体行使查询、更正、复制、删除、限制处理和撤回同意等权利。对于依法构成向境外提供个人信息的场景，我们将在传输前完成适用的个人信息保护影响评估和其他法定程序，并通过独立勾选或弹窗取得单独同意；本政策的一般同意不替代该单独同意。",
        en: "The Hong Kong service environment is controlled by the operator named in this Policy, with Alibaba Cloud providing the cloud infrastructure. Purposes, methods and data categories are limited to those described here. You may exercise access, correction, copy, deletion, restriction and consent-withdrawal rights through account features or by contacting the operator at +86 4001082026. Where the transfer is legally treated as an overseas provision of personal information, we will complete the applicable personal-information protection impact assessment and other required procedure before transfer and obtain separate consent through an independent checkbox or prompt; general acceptance of this Policy does not replace that separate consent.",
      },
    ],
  },
  {
    id: "security",
    title: { zh: "存储与安全保护", en: "Storage and security" },
    paragraphs: [
      {
        zh: "我们采用 HTTPS 传输、密码摘要、敏感字段加密或脱敏、权限分级、访问审计、上传文件访问控制、备份和故障恢复等措施。只有因职责需要的人员可以在授权范围内访问个人信息。",
        en: "We use HTTPS, password hashing, encryption or masking of sensitive fields, role-based access, access audit, upload access control, backups and recovery measures. Personnel may access personal information only within the authorisation needed for their duties.",
      },
      {
        zh: "互联网服务不存在绝对安全。发生可能影响你权益的安全事件时，我们将依法采取补救措施，并通过站内通知、电话或其他适当方式告知事件影响和建议措施；依法需报告的，将向主管机关报告。",
        en: "No internet service is absolutely secure. If an incident may affect your rights, we will take legally required remediation and notify you through in-app notice, telephone or another suitable channel about the impact and recommended action, and report to the competent authority where required.",
      },
    ],
  },
  {
    id: "retention",
    title: { zh: "保存期限与删除", en: "Retention and deletion" },
    items: [
      {
        zh: "账号资料在账号存续及提供服务所必需期间保存；你更换、解绑或完成账号注销后删除或匿名化，但依法或为解决未完履约、账务、争议、安全事件而确有必要保留的除外。",
        en: "Account data is retained while the account exists and as needed to provide the service. It is deleted or anonymised after replacement, unbinding or completed account deletion, except where retention is necessary for law, unfinished fulfilment, accounting, disputes or security incidents.",
      },
      {
        zh: "账号找回验证码和重置票据通常在 30 分钟内失效；邮件队列中的已完成或终止投递记录按系统清理策略通常在 24 小时后清理。绑定邮箱本身保留至你更换、解绑或完成账号注销。",
        en: "Account-recovery verification and reset tickets normally expire within 30 minutes. Completed or terminated delivery records in the mail queue are normally cleaned after 24 hours under the system policy. The bound recovery email remains until you replace or unbind it or complete account deletion.",
      },
      {
        zh: "为在网络异常后查询注销状态，设备上的注销回执最长保留 7 天，并在完成、过期或你主动清理时删除。必要的网络与安全日志仅在履行适用法律、安全审计和故障处理所需期间保存，具体期限由实际日志策略和适用要求确定。",
        en: "To check deletion status after a network interruption, the on-device deletion receipt is retained for no more than seven days and removed when completed, expired or manually cleared. Necessary network and security logs are retained only as long as required by applicable law, security audit and troubleshooting, with the actual period determined by the deployed logging policy and applicable requirements.",
      },
      {
        zh: "订单、结算、投诉和争议记录仅在完成履约、法定会计或监管义务、处理争议及审计所需期间受限保存；我们不会在未核实适用义务前虚构统一的固定财务保存年限。备份会按受控周期覆盖，并在恢复后重新执行适用的删除要求。",
        en: "Order, settlement, complaint and dispute records are kept with restricted access only as long as needed for fulfilment, applicable accounting or regulatory duties, disputes and audit. We do not invent a single fixed financial retention period before confirming the applicable duty. Backups are overwritten on a controlled cycle, and applicable deletions are re-applied after restoration.",
      },
    ],
  },
  {
    id: "rights",
    title: { zh: "你的权利与选择", en: "Your rights and choices" },
    paragraphs: [
      {
        zh: "你可在账号设置和相应业务页面查询、更正或补充资料，管理找回邮箱、地址、银行卡、KAI 身份关联和系统权限；可删除自己发布的可删除内容、撤回可撤回的同意，或申请复制、删除个人信息。撤回同意不影响撤回前处理的合法性。",
        en: "In account settings and the relevant service page, you can access, correct or supplement data and manage your recovery email, addresses, bank cards, KAI identity link and system permissions. You may delete your own deletable content, withdraw revocable consent, or request a copy or deletion of personal information. Withdrawal does not affect the lawfulness of earlier processing.",
      },
      {
        zh: "你可通过账号注销页面检查未结事项并申请注销。注销完成后，ZTW 登录会话和 KAI 登录关联失效，并清理可删除资料；注销 ZTW 不会注销外部 KAI 账号。若页面暂时无法完成请求，可通过本政策所列电话联系我们。我们通常在核验身份后 15 个工作日内答复。",
        en: "You can review outstanding items and request deletion on the account-deletion page. Once completed, ZTW sessions and the KAI sign-in link are disabled and deletable data is cleared. Deleting ZTW does not delete the external KAI account. If the page cannot complete your request, contact us by the telephone number in this policy. We normally respond within 15 working days after identity verification.",
      },
    ],
  },
  {
    id: "automated-decisions",
    title: { zh: "自动化决策与行情说明", en: "Automated decisions and market data" },
    paragraphs: [
      {
        zh: "ZTW 可使用规则进行登录风控、重复请求识别和内容安全检查，但不会仅凭自动化决策对你作出具有重大影响且无法申诉的决定。需要人工审核的实名、商家、交付、争议或账户事项由授权人员处理。",
        en: "ZTW may use rules for sign-in risk control, duplicate-request detection and content-safety checks, but does not make solely automated decisions that significantly affect you without a way to appeal. Identity, supplier, fulfilment, dispute and account matters requiring human review are handled by authorised personnel.",
      },
      {
        zh: "算力报价、K 线和市场统计用于信息展示和撮合参考，不代表个人画像、投资建议、即时库存或必然成交结果。",
        en: "Compute quotes, candlesticks and market statistics are for information and matching reference only; they are not personal profiling, investment advice, real-time inventory or a guarantee of a completed transaction.",
      },
    ],
  },
  {
    id: "minors",
    title: { zh: "未成年人保护", en: "Minors" },
    paragraphs: [
      {
        zh: "ZTW 面向具有完全民事行为能力的成年人，不向未满 18 周岁的人提供注册和交易服务。未满 18 周岁请勿注册、提交实名资料或使用撮合服务；如我们发现误收集，将在核实后依法删除或采取其他必要措施。",
        en: "ZTW is intended for adults with full civil capacity and does not offer registration or transaction services to anyone under 18. If you are under 18, do not register, submit identity data or use matching services. If we learn that data was collected in error, we will delete it or take other necessary measures after verification.",
      },
    ],
  },
  {
    id: "changes",
    title: { zh: "政策更新与联系", en: "Policy updates and contact" },
    paragraphs: [
      {
        zh: "功能、处理目的、第三方服务或法律要求发生重大变化时，我们会更新版本和日期，并通过页面提示、站内通知或重新征求同意等适当方式告知。未经依法告知和取得必要同意，不会用更新后的政策追溯扩大处理范围。",
        en: "If features, processing purposes, third-party services or legal requirements change materially, we will update the version and date and notify you through a page notice, in-app message or renewed consent as appropriate. We will not retroactively expand processing under an updated policy without legally required notice and consent.",
      },
      {
        zh: "如对本政策、个人信息处理或权利请求有疑问，请使用页面底部的唯一公开联系方式联系我们。",
        en: "For questions about this policy, personal-information processing or a rights request, use the sole public contact method shown below.",
      },
    ],
  },
];

export default function PrivacyPage() {
  return (
    <SimplePage
      title="隐私政策"
      titleEn="Privacy Policy"
      description="说明 ZTW 如何收集、使用、共享、保存和保护个人信息，以及你可以如何行使相关权利。"
      descriptionEn="How ZTW collects, uses, shares, retains and protects personal information, and how you can exercise your rights."
    >
      <LegalDocument sections={privacySections} accountDeletionLink />
    </SimplePage>
  );
}
