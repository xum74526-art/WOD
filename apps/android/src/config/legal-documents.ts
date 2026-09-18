import type { AppLanguage } from '../utils/language.ts'
import { toTraditionalChinese } from '../utils/traditional-chinese.ts'

export type LegalDocumentKind = 'agreement' | 'privacy'

export interface LegalSection {
  title: string
  paragraphs: string[]
}

export interface LegalDocument {
  title: string
  metadata: Array<{ label: string; value: string }>
  introduction: string[]
  sections: LegalSection[]
}

export const LEGAL_VERSION = '1.1'
export const LEGAL_UPDATED_AT = '2026-09-18'
export const LEGAL_EFFECTIVE_AT = '2026-09-18'
export const LEGAL_OPERATOR = '锆芯期算人工智能科技（上海）有限公司'
export const LEGAL_ADDRESS = '上海市浦东新区川南奉公路5058号3幢一层（集中登记地）'
export const LEGAL_ICP_FILING = '沪ICP备2026046279号-1'
export const LEGAL_CONTACT_PHONE = '+86 4001082026'

function metadataZh(): LegalDocument['metadata'] {
  return [
    { label: '版本', value: LEGAL_VERSION },
    { label: '更新日期', value: LEGAL_UPDATED_AT },
    { label: '生效日期', value: LEGAL_EFFECTIVE_AT },
    { label: '运营主体', value: LEGAL_OPERATOR },
    { label: '注册地址', value: LEGAL_ADDRESS },
    { label: '网站 ICP 备案', value: LEGAL_ICP_FILING },
  ]
}

function metadataEn(): LegalDocument['metadata'] {
  return [
    { label: 'Version', value: LEGAL_VERSION },
    { label: 'Last updated', value: LEGAL_UPDATED_AT },
    { label: 'Effective date', value: LEGAL_EFFECTIVE_AT },
    { label: 'Operator', value: LEGAL_OPERATOR },
    { label: 'Registered address', value: LEGAL_ADDRESS },
    { label: 'Website ICP filing', value: LEGAL_ICP_FILING },
  ]
}

const PRIVACY_ZH: LegalDocument = {
  title: '隐私政策',
  metadata: metadataZh(),
  introduction: [
    '本政策适用于算力星图移动客户端。我们重视你的个人信息与隐私，并按照合法、正当、必要和诚信原则处理个人信息。请在注册、登录或使用服务前完整阅读本政策。',
    '运营者及个人信息处理者为锆芯期算人工智能科技（上海）有限公司。若你不同意本政策，请停止注册或使用；拒绝非必要权限不会影响不依赖该权限的功能。',
  ],
  sections: [
    {
      title: '一、我们处理的信息与目的',
      paragraphs: [
        '1. 账号与登录：手机号码、用户名或昵称、经单向散列处理的密码、登录会话及账号状态，用于注册、登录、身份识别、风险控制和保障账号安全。当前手机号仅作为登录标识，未接入短信验证时不代表平台已核验号码归属。',
        '2. 账号找回：你主动绑定的找回邮箱、验证码发送及校验状态、短时有效的找回或重置凭据，用于验证邮箱并重置密码。我们不会在页面公开找回邮箱。',
        '3. KAI 身份关联：你主动登录或绑定时取得的关联身份标识、授权结果、一次性绑定凭据，以及 KAI 在授权范围内返回的邮箱、姓名和头像，用于登录、把本平台账号与 KAI 统一身份关联及完善你确认的个人资料；本平台不会索取或保存你的 KAI 密码。',
        '4. 个人资料与实名认证：昵称、头像、真实姓名、证件号码、证件正反面图片、格式校验结果及审核状态，用于个人资料展示、实名认证、商家准入和风险控制。证件图片仅供受权人员核验；服务器使用本地 Tesseract OCR 生成比对结果，不将证件图片发送给第三方 OCR 服务。',
        '5. 业务资料：银行卡登记信息以加密方式保存并仅展示掩码；地址信息用于用户主动选择的业务联系或交付。买方需求可能包含联系人、电话、算力型号、数量、期限、地区和需求说明；商家资料可能包含主体、联系人、资源、设备和交付信息。',
        '6. 撮合、订单与交付：需求、报价、反报价、方案确认、订单、卡时或账务记录、结算、退款、争议及历史状态，用于撮合沟通、履约、对账、售后和争议处理。商家提交的 SSH 地址、端口、用户名和凭据仅用于经确认的交付，并按角色限制展示。',
        '7. 资讯与社区：你主动发布或上传的文字、图片、视频、评论、点赞及互动记录，用于展示、内容管理和处理举报。公开发布的内容会向其他用户展示，请勿上传证件、银行卡、密码或其他不宜公开的信息。',
        '8. 客服与工单：咨询内容、工单、附件、处理状态和必要的账号关联信息，用于答复问题、跟进服务及处理投诉。',
        '9. 设备、网络和日志：应用版本、设备型号、操作系统版本、IP 地址、网络状态、崩溃与操作日志，以及运行环境实际提供的设备标识符，用于运行应用、兼容性分析、安全防护、故障诊断和防止滥用。我们不以此建立与服务无关的画像。',
      ],
    },
    {
      title: '二、系统权限',
      paragraphs: [
        '1. 网络权限用于登录、获取行情与资讯、提交需求、上传内容和联系客服。',
        '2. 当你主动上传头像或身份认证资料时，Android 可能申请照片/媒体访问权限并调用系统拍摄入口，iOS 可能申请相机或照片权限。当前审核版本关闭社区媒体发布且不申请麦克风权限；若未来启用含声音的视频录制，我们会先更新权限说明和适用规则。相关权限不会在无关场景调用，你可在系统设置中撤回。',
        '3. 我们不申请通讯录权限，也不持续获取精确位置。关闭某项可选权限后，只会影响依赖该权限的拍摄、选择或上传功能。',
      ],
    },
    {
      title: '三、我们如何使用信息',
      paragraphs: [
        '我们仅在实现上述功能、履行协议、遵守法定义务、保障账号和系统安全、处理争议以及经你另行同意的范围内使用个人信息。若处理目的、方式或信息种类发生实质变化，我们会更新说明，并在依法需要时重新取得同意。',
        '我们不会出售个人信息，不会以同意本政策为由强制你提供与当前功能无关的信息，也不会将个人信息用于与算力星图服务无关的自动化营销。',
        '身份证件和银行卡资料属于敏感个人信息，一旦泄露或滥用可能造成身份冒用或财产损失。我们仅在实名认证、经授权的银行卡业务等特定且充分必要的目的下处理，并在进入对应功能时依法取得单独同意，采取加密、掩码、最小权限和访问审计等强化保护措施。精确的 SSH 等交付凭据按高敏业务秘密实施加密、最小权限和访问审计，但不在尚未实现单独同意的流程中宣称已取得该同意。',
      ],
    },
    {
      title: '四、受托处理与第三方服务',
      paragraphs: [
        '1. 阿里云中国香港区域（cn-hongkong）：作为云基础设施受托方，为核心 API、数据库、上传文件、备份与安全防护提供计算和存储能力，可能处理本政策列明的账号、实名、业务、内容及日志信息。服务区域位于中国香港特别行政区。',
        '2. DCloud uni-app 基础运行框架（开发者：数字天堂（北京）网络技术有限公司）：在你同意隐私政策后，为应用运行、页面渲染、兼容性、安全和故障分析，可能处理设备品牌与型号、操作系统、应用版本、网络类型、IP 地址、User-Agent、运行日志，以及打包组件可能涉及的 OAID。本项目不将这些信息用于广告或个性化推荐；实际范围以后续正式安装包检测结果和应用内第三方 SDK 清单为准。',
        '3. KAI 统一身份服务：仅在你主动选择 KAI 登录或绑定时处理授权请求、关联身份标识、回跳参数、一次性凭据，以及授权范围内返回的邮箱、姓名和头像，以完成登录、身份关联及你确认的资料展示。',
        '4. 哔哩哔哩：当你打开来自哔哩哔哩的资讯视频时，播放器或接口会向其请求内容，并可能传递 IP 地址、网络与浏览器或应用请求信息；其处理同时受哔哩哔哩隐私规则约束。',
        '5. 网易 163 邮件服务：当你绑定找回邮箱、获取验证码或重置密码时，用于投递必要邮件，可能处理收件邮箱、邮件内容、投递时间与状态。SMTP 授权信息仅保存在服务端，不向客户端公开。',
        '6. 七相支付（Qixiang Pay）：当前审核版默认关闭在线支付。仅在未来直接交易能力由服务端和客户端同时启用、你主动发起支付且已完成必要提示时，才会处理完成支付所需的订单号、金额、回调状态等最少信息。',
        '我们会通过合同、权限控制和安全要求约束受托方。第三方作为独立处理者时，其服务还受其公开规则约束；具体功能未启用或你未主动使用时，不会因本条说明而自动向其提供业务资料。',
      ],
    },
    {
      title: '五、共享、转移与公开披露',
      paragraphs: [
        '除为完成你主动请求的撮合与交付、履行法定义务、保护人身财产安全或取得你的单独同意外，我们不会向其他主体共享个人信息。撮合时只向相关方提供完成沟通或履约必要的信息，不在公开需求市场直接展示买方私人联系方式。',
        '发生合并、分立、重组或业务转移时，我们会依法告知接收方并要求其继续受本政策约束。除你主动公开的社区内容、依法披露或取得单独同意外，我们不会公开披露个人信息。',
      ],
    },
    {
      title: '六、存储地点、跨境处理与期限',
      paragraphs: [
        '当前算力星图核心 API、数据库及上传文件部署在阿里云中国香港区域（cn-hongkong）。所有地区的用户使用业务联网功能时，本政策列明的账号、找回邮箱、KAI 关联、实名与银行卡、地址、撮合交易与 SSH 交付、社区客服、设备网络及日志信息，会通过加密传输发送至中国香港特别行政区并在那里存储和处理，用于提供服务、履约、安全防护、故障处理及依法保存。',
        '该中国香港服务环境由本政策所列运营主体控制，云基础设施服务商为阿里云；处理目的、方式和信息种类限于本政策所列范围。移动客户端无论选择中国大陆或其他服务地区，都会在业务网络请求前通过独立勾选要求你明确确认上述香港存储、处理与必要传输，所选地区仍保存在本机用于适用规则判断。你可通过账号功能或上述联系电话向运营主体行使相关权利。对于依法构成向境外提供个人信息的场景，我们将在传输前完成适用的个人信息保护影响评估和其他法定程序并取得单独同意；本政策的一般同意不替代该单独同意。',
        '账号与业务资料仅在提供服务、处理争议或履行法定义务所需期间保留。找回邮箱验证码与密码重置凭据默认三十分钟失效，邮件投递终态记录在完成后按系统策略清理，默认不超过二十四小时。',
        '注销流程在本设备保存的专用恢复凭据、到期时间和内部账号编号最长保留七天，不包含密码或普通登录令牌。头像、证件、地址、社区、客服等资料在目的完成、用户删除或账号注销后删除或匿名化，但未履约、账务、结算、争议及依法必须保留的材料会在必要范围和期限内受限保留，不预设超出法律与业务需要的固定年限。',
        '在法律法规要求时，网络安全日志按要求保留。备份会在受控周期内覆盖；如从备份恢复，系统会重新执行已完成的注销清理。期限届满后，我们会删除或匿名化相关信息。',
      ],
    },
    {
      title: '七、安全措施与事件处置',
      paragraphs: [
        '我们采取传输加密、密码单向散列、敏感字段加密或掩码、角色与最小权限控制、访问审计、限流、备份和漏洞修复等措施。互联网服务无法保证绝对安全；如发生可能影响你权益的安全事件，我们会依法采取补救措施并履行通知或报告义务。',
        '请妥善保管密码、验证码、找回凭据和 SSH 凭据，不要通过社区或公开留言发送敏感信息。发现异常时请及时修改密码并联系我们。',
      ],
    },
    {
      title: '八、你的权利',
      paragraphs: [
        '你可以在个人中心查看或更正资料、管理找回邮箱、删除符合条件的银行卡和地址、管理发布内容、撤回系统权限，或联系我们申请访问、更正、复制、删除、限制处理、解释处理规则及撤回同意。撤回同意不影响此前基于同意进行处理的合法性。',
        '你可以从“我的 → 设置 → 注销账号”提交注销。未履约、争议或待结算事项需先处理；注销完成后全部设备会话失效、非必要资料会被清理，并解除本平台的 KAI 绑定，但不会删除其他 KAI 产品账号。注销不可恢复，重新注册不会继承原账号记录。',
        '为保障账号安全，我们可能要求核验身份。我们通常会在十五个工作日内答复；情况复杂或法律另有规定的，按适用规则处理。',
      ],
    },
    {
      title: '九、未成年人保护',
      paragraphs: [
        '本平台面向年满十八周岁的用户。未满十八周岁者不得注册或使用需要成年身份的服务。实名认证审核可能识别并拒绝不符合年龄要求的申请，但这不代表平台在注册阶段已完成年龄核验。若我们发现误收集未成年人信息，会依法尽快处理。',
      ],
    },
    {
      title: '十、政策更新',
      paragraphs: [
        '我们可能因功能、处理活动或法律要求变化而更新本政策，并在应用内或网站公布新版本。涉及处理目的、方式、信息种类或你的权利的重大变化时，我们会以显著方式提示，并在依法需要时重新取得同意。',
      ],
    },
    {
      title: '十一、联系我们',
      paragraphs: [
        `联系我们：${LEGAL_CONTACT_PHONE}`,
        `运营主体：${LEGAL_OPERATOR}。注册地址：${LEGAL_ADDRESS}。你可通过上述电话咨询隐私、账号、投诉或权利请求。`,
      ],
    },
  ],
}

const PRIVACY_EN: LegalDocument = {
  title: 'Privacy Policy',
  metadata: metadataEn(),
  introduction: [
    'This Policy applies to the 算力星图 mobile applications. We process personal information lawfully, fairly, only as necessary, and in good faith. Please read it before registering, signing in, or using the service.',
    `The operator and personal-information processor is ${LEGAL_OPERATOR}. If you do not agree, do not register or continue using the service. Refusing an optional permission affects only the feature that needs it.`,
  ],
  sections: [
    {
      title: '1. Information we process and why',
      paragraphs: [
        'Account and access data includes your mobile number, username or nickname, one-way password hash, sessions, and account status. We use it for registration, sign-in, identification, risk control, and account security. Until SMS verification is enabled, a mobile number is only a login identifier and does not prove ownership.',
        'Account recovery data includes an email address you choose to bind, verification and delivery status, and short-lived recovery or reset credentials. It is used only to verify the address and reset the password, and is not displayed publicly.',
        'When you choose KAI sign-in or binding, we process the linked identity identifier, authorization result, one-time binding credential, and the email address, name, and avatar returned by KAI within the authorized scope. We use them for sign-in, identity linking, and profile details you confirm. We never request or store your KAI password.',
        'Profile and verification data may include your nickname, avatar, legal name, national ID number, front and back ID images, validation results, and review status. Server-side local Tesseract OCR produces comparison results; ID images are not sent to a third-party OCR provider.',
        'Business data may include encrypted and masked bank-card details, addresses, buyer contact and compute requirements, merchant identity and contact materials, resource and device descriptions, and delivery details.',
        'Matchmaking, order, and fulfillment data may include requirements, proposals, counteroffers, confirmations, orders, CH or ledger entries, settlement, refunds, disputes, history, and seller-provided SSH host, port, username, and credentials. SSH details are role-restricted and used only for confirmed fulfillment.',
        'Community, content, and support data includes posts, images, videos, comments, reactions, reports, support conversations, tickets, attachments, and status. Public content is visible to other users, so never post IDs, cards, passwords, or other sensitive data.',
        'Technical data may include app version, device model, operating-system version, IP address, network state, crash and operation logs, and device identifiers actually made available by the runtime. We use it for compatibility, security, troubleshooting, and abuse prevention, not unrelated profiling.',
      ],
    },
    {
      title: '2. System permissions',
      paragraphs: [
        'Network access supports sign-in, pricing, content, requirements, uploads, and support. When you actively upload an avatar or identity-verification material, Android may request photo/media access and may invoke a system capture entry, while iOS may request camera or photo access. The current review build disables community media publishing and does not request microphone access. If video recording with sound is enabled later, we will first update the permission notice and applicable terms.',
        'We do not request contacts access or continuously collect precise location. You may withdraw optional permissions in system settings without affecting unrelated features.',
      ],
    },
    {
      title: '3. Use, entrusted processing, and third parties',
      paragraphs: [
        'We use data only to provide the described services, perform agreements, comply with law, secure accounts and systems, resolve disputes, or as separately authorized. We do not sell personal information or use it for unrelated automated marketing.',
        'Identity documents and bank-card details are sensitive personal information. Misuse or disclosure may create identity or financial risk. We process them only for specific and strictly necessary purposes such as identity review or an authorized card function, obtain separate consent in the relevant feature where required by law, and apply enhanced encryption, masking, least-privilege, and access-audit safeguards. Precise SSH and other delivery credentials are protected as high-risk business secrets through encryption, least privilege, and access auditing; we do not claim separate consent where that workflow is not implemented.',
        'Alibaba Cloud Hong Kong region (cn-hongkong), as the contracted cloud-infrastructure provider, supplies compute, storage, backup, and security capabilities for the core API, database, and uploaded files, and may process the account, identity, business, content, and log data described in this Policy. The service region is Hong Kong SAR.',
        'The DCloud uni-app base runtime (developer: Digital Paradise (Beijing) Network Technology Co., Ltd.) may, after you accept this Policy, process device brand and model, operating system, app version, network type, IP address, User-Agent, runtime logs, and OAID that may be present in packaged components for runtime compatibility, security, and troubleshooting. 算力星图 does not use this data for advertising or personalized recommendations. The final scope follows inspection of the released package and the in-app third-party SDK list.',
        'KAI identity services process authorization requests, linked identifiers, return parameters, one-time credentials, and the email address, name, and avatar returned within the authorized scope only when you initiate sign-in or binding. Bilibili receives a content request and may receive IP, network, and user-agent or app request information when you open Bilibili-hosted news video.',
        'NetEase 163 mail services deliver verification and password-recovery messages and may process recipient address, message, delivery time, and status. SMTP credentials remain server-side. QiXiang Pay is disabled by default in the review build; minimum order, amount, and callback data is processed only if direct trading is later enabled on both server and client, you initiate payment, and the required notice is shown.',
        'We contractually restrict processors. An independent third party is also governed by its own published rules. A listed integration does not receive business data unless the feature is enabled and you use it.',
      ],
    },
    {
      title: '4. Sharing, transfer, and disclosure',
      paragraphs: [
        'We share only the minimum data needed for matchmaking or fulfillment you request, legal obligations, protection of people or property, or with separate consent. Buyer contact details are not displayed in the public requirement market.',
        'For a merger, split, restructuring, or business transfer, we will notify the recipient and require continued protection. We disclose data publicly only when you publish community content, law requires it, or you separately consent.',
      ],
    },
    {
      title: '5. Storage location, cross-border processing, and retention',
      paragraphs: [
        '算力星图 currently deploys its core API, database, and uploaded files in Alibaba Cloud Hong Kong region (cn-hongkong). When users in any region use service network features, the account, recovery-email, KAI-link, identity and bank-card, address, matchmaking and SSH-delivery, community and support, device/network and log data described in this Policy is encrypted in transit to Hong Kong SAR and stored and processed there for service delivery, fulfillment, security, troubleshooting, and legally required retention.',
        'The Hong Kong service environment is controlled by the operator named in this Policy, with Alibaba Cloud providing the cloud infrastructure. Purposes, methods, and data categories are limited to those described here. In the mobile apps, whether you select mainland China or another service region, an independent checkbox requires your explicit confirmation of that Hong Kong storage, processing, and necessary transfer before the app starts its business network requests; the region choice remains stored on your device to determine applicable rules. You may exercise your rights through account features or the contact number above. Where the transfer is legally treated as an overseas provision of personal information, we will complete the applicable personal-information protection impact assessment and other required procedure before transfer and obtain separate consent; general acceptance of this Policy does not replace that separate consent.',
        'Account and business data is retained only for service, dispute, or legal needs. Recovery verification and reset credentials expire in 30 minutes. Completed recovery-mail delivery records are normally removed within 24 hours.',
        'A deletion recovery capability, expiry, and internal account ID may remain on this device for up to seven days; it contains no password or normal login token. Profile, ID, address, community, and support data is deleted or anonymized when its purpose ends, you delete it, or the account is deleted. Unfulfilled, ledger, settlement, dispute, and legally required records remain restricted only for the necessary scope and period, without inventing a fixed financial term.',
        'Security logs are retained when and for as long as law requires. Backups are overwritten on a controlled cycle, and completed deletion cleanup is reapplied after restoration. Expired data is deleted or anonymized.',
      ],
    },
    {
      title: '6. Security and incidents',
      paragraphs: [
        'We use encrypted transport, one-way password hashing, encryption or masking of sensitive fields, role and least-privilege controls, access auditing, rate limits, backups, and vulnerability remediation. No Internet service is absolutely secure. We will take remedial action and provide legally required notice or reporting after a relevant security incident.',
        'Protect passwords, verification codes, recovery and SSH credentials, and never post them publicly. Change your password and contact us if you suspect misuse.',
      ],
    },
    {
      title: '7. Your rights and account deletion',
      paragraphs: [
        'You can view or correct profile data, manage recovery email, delete eligible cards and addresses, manage content, withdraw system permissions, or contact us to request access, correction, copies, deletion, restriction, an explanation, or withdrawal of consent. Withdrawal does not affect processing already lawfully completed.',
        'Use Profile → Settings → Delete account. Active fulfillment, disputes, or unsettled matters must be resolved first. Completion invalidates all sessions, removes unnecessary data, and unlinks the 算力星图 KAI identity without deleting other KAI products. Deletion cannot be reversed and a new account does not inherit old records.',
        'We may verify identity before acting on a request and normally respond within 15 working days, subject to applicable law and complex cases.',
      ],
    },
    {
      title: '8. Minors',
      paragraphs: ['The Platform is intended for users aged 18 or older. A person under 18 must not register or use adult-only services. Identity review may reject an underage application, but this does not mean age is already verified at registration. We will promptly address information collected in error.'],
    },
    {
      title: '9. Updates and contact',
      paragraphs: [
        'We may update this Policy for changes in features, processing, or law and publish the new version in the app or on the website. We will prominently notify material changes and obtain renewed consent where required.',
        `Contact us: ${LEGAL_CONTACT_PHONE}`,
        `Operator: ${LEGAL_OPERATOR}. Registered address: ${LEGAL_ADDRESS}. Use the phone above for privacy, account, complaint, or rights requests.`,
      ],
    },
  ],
}

function agreementZh(): LegalDocument {
  const transactionSection: LegalSection = {
    title: '五、当前撮合模式与条件性直接交易',
    paragraphs: [
      '当前审核版默认采用撮合模式，不开放新充值、新提现或在线收取交易款项，不扣减或冻结卡时，不自动创建直接交易订单或算力资产，也不承诺固定收益。',
      '已存在的钱包、充值、提现、订单和资产记录仅用于查询历史与处理未结事项。卡时是平台业务记账单位，不是现金、存款、理财产品或无条件可兑付资产；状态及可执行操作以服务端返回为准。',
      '未来直接交易仅会在服务端能力和客户端构建同时启用、必要资质和流程完成，并向你另行展示适用规则后开放。届时算力市场可分为 KAI 自营和入驻资料已审核商家资源，算力订单仅按整数小时购买，并会在提交前展示标的、数量、期限、价格、费用、支付、冻结、交付、验收、取消、退款和结算规则。启用时将升级适用协议版本，并在依法需要时重新取得同意；客户端页面或跳转结果本身不构成入账凭证。',
    ],
  }

  return {
    title: '用户协议',
    metadata: metadataZh(),
    introduction: [
      '本协议由你与锆芯期算人工智能科技（上海）有限公司就算力星图移动客户端及相关服务共同订立。请在注册、登录或使用前完整阅读，尤其是风险提示、责任限制、账号注销和争议解决条款。',
      '点击同意、注册、登录或继续使用即表示你已阅读并接受本协议及届时适用的页面规则；如不同意，请停止注册或使用。',
    ],
    sections: [
      {
        title: '一、主体与协议范围',
        paragraphs: [
          `平台运营主体为${LEGAL_OPERATOR}，注册地址为${LEGAL_ADDRESS}。网站 ICP 备案为${LEGAL_ICP_FILING}。`,
          '本协议适用于算力行情与资讯、资源目录、需求撮合、商家协作、社区、客服、账号及历史记录等功能。某项功能未启用时，本协议中的条件性说明不表示该功能已经开放。',
        ],
      },
      {
        title: '二、账号注册、登录与安全',
        paragraphs: [
          '你应提供真实、合法且属于自己的注册资料。当前手机号在未接入短信验证时仅作为登录标识，不代表平台已核验号码归属；不得使用他人号码、冒用身份或转让账号。',
          '你可以主动绑定找回邮箱或 KAI 身份。找回邮箱用于验证码和重置密码；KAI 绑定仅关联身份，不会要求你向本平台提供 KAI 密码。你应妥善保管密码、验证码、找回凭据和设备，因自身保管不当造成的风险由你依法承担。',
          '平台会采取合理安全措施，并可对异常登录、批量注册、接口滥用或高风险操作进行验证、限流、暂停或人工核查。若发现账号异常，请立即修改密码并联系我们。',
        ],
      },
      {
        title: '三、服务内容与使用条件',
        paragraphs: [
          '平台提供 KAI Pricing 行情参考、算力资源信息、需求提交、商家方案与反报价、双方确认、人工协调交付、资讯社区、客服及历史查询。平台可根据合规、资质、系统或运营情况调整可用功能。',
          '实名认证、商家申请、内容发布、敏感操作或特定履约环节可能需要补充真实资料并通过审核。审核通过仅代表材料在审核时满足准入要求，不等于平台对持续履约能力、硬件性能或收益作担保。',
        ],
      },
      {
        title: '四、行情、资源与需求撮合',
        paragraphs: [
          'KAI Pricing 及其他行情、K 线、报价、配置、可用数量和历史数据用于市场观察与需求沟通，不构成投资建议、即时库存、固定报价、成交承诺或收益保证。数据可能受上游更新、网络、样本量和时间窗口影响。',
          '你可提交型号、数量、期限、地区、联系方式和说明；提交需求不等于下单、付款或签订合同。资料已审核的商家可提交方案，平台可协助比较、联系和确认。最终服务范围、价格、交付、验收、费用、违约责任应由相关方在实际确认时确定。',
          '买方私人联系方式不会在公开需求市场直接展示。用户应独立核验方案并审慎决策，不得将行情或平台协调理解为平台代替交易方承担全部履约责任。',
        ],
      },
      transactionSection,
      {
        title: '六、商家与 SSH 交付',
        paragraphs: [
          '商家应确保主体、联系人、资源配置、权属或合法使用权、可用量、价格和交付说明真实准确，并及时更新状态。平台对入驻资料的审核不构成对硬件、持续库存、收益或全部陈述的认证。',
          '商家仅可为已确认的履约提交必要 SSH 主机、端口、用户名和凭据，不得复用弱口令或提交无权提供的系统。买方仅可在约定范围内使用，不得转交、扫描、攻击、绕过权限或从事违法活动。双方应在交付后及时更换或撤销临时凭据。',
          '平台可为履约协调和争议处理在最小范围内展示或保留交付记录。因交易方提供错误资料、超范围使用或未遵守安全要求造成的责任，由过错方依法承担。',
        ],
      },
      {
        title: '七、费用、返佣与展示信息',
        paragraphs: [
          '当前撮合模式不因展示资源或提交需求自动收费。未来启用收费、支付、平台服务费、磨损、返佣或奖励时，适用标准、条件、计算基数、上限、结算时间和失效情形以操作前明确展示并由服务端确认的规则为准。',
          '页面中的预计值、未结算记录、等级或进度不构成兑付承诺。任何奖励不得通过虚假交易、刷单、自买自卖、批量账号或其他不正当方式取得。',
        ],
      },
      {
        title: '八、资讯与社区',
        paragraphs: [
          '你对发布的文字、图片、视频、评论及其他内容负责，并保证拥有必要权利。不得发布违法、侵权、虚假、欺诈、恶意营销、泄露隐私、攻击系统或妨害他人权益的内容。',
          '为提供展示、转码、审核和传播功能，你授予平台在服务范围内必要、非独占、可撤回（法律或已完成传播另有要求除外）的使用许可。平台可依法采取屏蔽、删除、限制传播、保存证据或报告等措施。外部视频来源同时受来源平台规则约束。',
        ],
      },
      {
        title: '九、禁止行为',
        paragraphs: [
          '不得实施欺诈、洗钱、侵权、虚假交易、刷量、恶意占用资源、绕过风控、未经授权访问、上传恶意代码、干扰接口或网络、倒卖账号、抓取非公开数据，以及法律法规禁止或损害平台与他人权益的行为。',
          '平台可根据行为性质采取提示、限制功能、撤下内容、暂停交易或账号、保存证据和配合主管机关等措施；涉及款项、资产或争议的处理仍应遵循服务端记录、适用规则和法律。',
        ],
      },
      {
        title: '十、知识产权',
        paragraphs: [
          '平台软件、界面、标识、文档和依法享有权利的数据受知识产权法律保护。未经许可，不得复制、反向工程、出售、出租或用于建立竞争性服务。第三方内容和标识归相应权利人所有。',
        ],
      },
      {
        title: '十一、服务变更、中断与终止',
        paragraphs: [
          '因维护、升级、网络、上游、不可抗力、监管要求或安全风险，服务可能调整、中断或终止。平台会在合理范围内提前通知并尽力降低影响，但紧急安全或合规情形可先行处置。',
          '你可按“我的 → 设置 → 注销账号”申请注销。未履约、争议和待结算事项须先处理；注销不当然免除已发生的义务。完成后无法恢复，重新注册不继承原记录，依法或为解决争议必须保留的材料将在必要范围内受限保存。',
        ],
      },
      {
        title: '十二、风险与责任边界',
        paragraphs: [
          '你应根据自身用途、技术能力、预算与风险承受能力独立判断。平台不保证行情持续无误、资源随时可用、服务不中断、商家必然履约或获得任何收益。',
          '因平台故意或重大过失造成损失的，依法承担责任；因用户或交易方过错、第三方服务、上游中断、网络设备故障、不可抗力或平台无法合理控制的事件造成的影响，按法律和各方过错处理。本条不排除法律规定不得限制的责任。',
        ],
      },
      {
        title: '十三、协议更新与争议解决',
        paragraphs: [
          '平台可因功能、规则或法律变化更新协议并公布生效日期。重大变更会以显著方式提示；若依法需要，将重新取得同意。变更前已产生的权益与义务按当时规则及法律处理。',
          '本协议适用中华人民共和国法律。争议应先友好协商；协商不成，可向运营主体住所地有管辖权的人民法院提起诉讼，但法律另有强制规定的除外。',
        ],
      },
      {
        title: '十四、联系我们',
        paragraphs: [
          `联系我们：${LEGAL_CONTACT_PHONE}`,
          `运营主体：${LEGAL_OPERATOR}。注册地址：${LEGAL_ADDRESS}。上述电话可用于业务咨询、账号问题、投诉和协议相关事项。`,
        ],
      },
    ],
  }
}

function agreementEn(): LegalDocument {
  const transactionSection: LegalSection = {
    title: '5. Current matchmaking mode and conditional direct trading',
    paragraphs: [
      'The review build uses matchmaking mode by default. It does not open new top-ups or withdrawals, collect transaction payments online, debit or freeze CH, automatically create direct orders or compute assets, or promise fixed returns.',
      'Existing wallet, top-up, withdrawal, order, and asset records are available only for history and outstanding matters. CH is a business ledger unit, not cash, a deposit, an investment product, or an unconditional redeemable asset. Server-authorized state controls available actions.',
      'Future direct trading opens only after both server and client enable it and required qualifications and workflows are complete. The market may then distinguish KAI Direct resources from offers by merchants with reviewed onboarding materials; compute orders use whole hours, and the item, quantity, duration, price, fees, payment, freeze, delivery, acceptance, cancellation, refund, and settlement rules are separately presented before submission. Enabling it will require an updated applicable agreement version and renewed consent where legally required. A client page or redirect alone is not proof of payment.',
    ],
  }

  return {
    title: 'User Agreement',
    metadata: metadataEn(),
    introduction: [
      `This Agreement is between you and ${LEGAL_OPERATOR} for the 算力星图 mobile applications and related services. Read it fully, especially the risk, liability, deletion, and dispute terms.`,
      'By accepting, registering, signing in, or continuing to use 算力星图, you accept this Agreement and the rules shown for a feature. If you disagree, do not register or use the service.',
    ],
    sections: [
      {
        title: '1. Operator and scope',
        paragraphs: [
          `The operator is ${LEGAL_OPERATOR}, registered at ${LEGAL_ADDRESS}. Website ICP filing: ${LEGAL_ICP_FILING}.`,
          'This Agreement covers compute pricing and news, resource directories, requirement matchmaking, merchant collaboration, community, support, accounts, and history. A conditional clause does not mean a disabled feature is currently available.',
        ],
      },
      {
        title: '2. Accounts and security',
        paragraphs: [
          'Provide truthful, lawful information that belongs to you. Until SMS verification is enabled, a mobile number is only a login identifier and does not prove ownership. Do not impersonate others, use their number, transfer an account, or share credentials.',
          'You may bind a recovery email or KAI identity. Recovery email supports verification and password reset. KAI binding links identities and never requires your KAI password. Protect passwords, codes, recovery credentials, SSH credentials, and devices.',
          'We may verify, rate-limit, suspend, or manually review unusual sign-in, bulk registration, API abuse, or high-risk activity. Change your password and contact us promptly if you detect misuse.',
        ],
      },
      {
        title: '3. Services and eligibility',
        paragraphs: [
          '算力星图 provides KAI Pricing market references, compute-resource information, requirement submission, merchant proposals and counteroffers, confirmation, coordinated fulfillment, community, support, and history. Availability may change for compliance, qualifications, security, or operations.',
          'Identity verification, merchant application, publishing, sensitive operations, or fulfillment may require accurate additional materials. Approval means the materials met admission requirements at review time; it is not a guarantee of continuing capacity, hardware performance, or returns.',
        ],
      },
      {
        title: '4. Market data and matchmaking',
        paragraphs: [
          'KAI Pricing and other quotes, charts, configurations, quantities, and historical data support observation and discussions only. They are not investment advice, live inventory, fixed quotations, transaction commitments, or return guarantees, and may be affected by upstream updates, networks, sample size, and time windows.',
          'A requirement may include model, quantity, duration, region, contact, and notes. Submission is not an order, payment, or contract. Merchants with reviewed onboarding materials may propose plans, and 算力星图 may coordinate comparison and confirmation. Final scope, price, delivery, acceptance, fees, and liability must be confirmed by the relevant parties.',
          'Buyer private contact details are not shown in the public market. Users must independently evaluate a plan and must not treat market data or coordination as 算力星图 assuming every counterparty obligation.',
        ],
      },
      transactionSection,
      {
        title: '6. Merchants and SSH delivery',
        paragraphs: [
          'Merchants must keep entity, contact, resource, lawful control, availability, price, and delivery details accurate. Review of onboarding materials is not certification of hardware, continuing inventory, returns, or every merchant statement.',
          'A merchant may submit only necessary SSH host, port, username, and credentials for confirmed fulfillment and must not reuse weak credentials or deliver a system it cannot lawfully provide. A buyer may use access only as agreed and must not reshare, scan, attack, bypass controls, or break law. Temporary credentials should be rotated or revoked promptly.',
          '算力星图 may display or retain minimum delivery records for coordination and disputes. A party at fault remains responsible for inaccurate materials, out-of-scope use, or failure to follow security requirements.',
        ],
      },
      {
        title: '7. Fees, rewards, and displayed amounts',
        paragraphs: [
          'Matchmaking mode does not automatically charge for viewing a resource or submitting a requirement. If fees, payment, service charges, wear charges, rebates, or rewards are enabled later, the standard, conditions, basis, cap, settlement time, and expiry shown before the action and confirmed by the server apply.',
          'Estimates, unsettled entries, tiers, and progress are not payout promises. Sham transactions, self-dealing, bulk accounts, manipulation, and other abuse are prohibited.',
        ],
      },
      {
        title: '8. News and community',
        paragraphs: [
          'You are responsible for posts, images, video, comments, and other content and must hold the necessary rights. Illegal, infringing, false, fraudulent, privacy-invasive, malicious, or system-abusive content is prohibited.',
          'You grant 算力星图 the necessary non-exclusive service-scope permission to display, transcode, review, and distribute submitted content. We may restrict or remove content, preserve evidence, and report as law requires. External video is also subject to the source platform rules.',
        ],
      },
      {
        title: '9. Prohibited conduct',
        paragraphs: [
          'Fraud, money laundering, infringement, sham transactions, manipulation, malicious resource reservation, bypassing controls, unauthorized access, malware, network or API disruption, account resale, scraping non-public data, and conduct prohibited by law or harmful to others are forbidden.',
          'Depending on severity, 算力星图 may warn, restrict features, remove content, suspend transactions or accounts, preserve evidence, and cooperate with authorities. Money, assets, and disputes remain governed by server records, applicable rules, and law.',
        ],
      },
      {
        title: '10. Intellectual property',
        paragraphs: ['The software, interfaces, marks, documents, and protected data belong to their lawful owners. Without permission, do not copy, reverse engineer, sell, rent, or use them to create a competing service. Third-party content and marks remain with their respective owners.'],
      },
      {
        title: '11. Changes, interruption, and termination',
        paragraphs: [
          'Maintenance, upgrades, network or upstream issues, force majeure, regulation, or security risk may change, interrupt, or end service. We will give reasonable advance notice where practical, but urgent security or compliance action may be immediate.',
          'You may request deletion at Profile → Settings → Delete account. Active fulfillment, disputes, and unsettled matters must be resolved first, and deletion does not erase existing obligations. Completion is irreversible; a new account does not inherit records. Legally or operationally necessary evidence remains restricted.',
        ],
      },
      {
        title: '12. Risk and liability',
        paragraphs: [
          'Evaluate your own purpose, technical ability, budget, and risk tolerance. 算力星图 does not guarantee uninterrupted or error-free data, constant resource availability, merchant performance, or any return.',
          '算力星图 remains liable where loss is caused by its intent or gross negligence as required by law. Effects caused by a user or counterparty, third-party or upstream interruption, network or device failure, force majeure, or events beyond reasonable control are allocated under law and fault. Nothing excludes liability that law does not permit us to limit.',
        ],
      },
      {
        title: '13. Updates and disputes',
        paragraphs: [
          'We may update this Agreement for feature, rule, or legal changes and publish its effective date. Material changes are prominently notified and renewed consent obtained where required. Existing rights and duties follow the rules and law applicable when they arose.',
          'The laws of the People’s Republic of China apply. Parties should first negotiate in good faith. If unresolved, proceedings may be brought in the competent court at the operator’s domicile, unless mandatory law provides otherwise.',
        ],
      },
      {
        title: '14. Contact us',
        paragraphs: [
          `Contact us: ${LEGAL_CONTACT_PHONE}`,
          `Operator: ${LEGAL_OPERATOR}. Registered address: ${LEGAL_ADDRESS}. Use the phone above for business, account, complaint, or agreement questions.`,
        ],
      },
    ],
  }
}

const PROTECTED_LEGAL_VALUES = [LEGAL_OPERATOR, LEGAL_ADDRESS, LEGAL_ICP_FILING] as const

function toTraditionalLegalText(value: string): string {
  let converted = toTraditionalChinese(value)
  for (const legalValue of PROTECTED_LEGAL_VALUES) {
    converted = converted.replaceAll(toTraditionalChinese(legalValue), legalValue)
  }
  return converted
}

function toTraditional(document: LegalDocument): LegalDocument {
  return {
    title: toTraditionalLegalText(document.title),
    metadata: document.metadata.map(({ label, value }) => ({
      label: toTraditionalLegalText(label),
      value: toTraditionalLegalText(value),
    })),
    introduction: document.introduction.map(toTraditionalLegalText),
    sections: document.sections.map((section) => ({
      title: toTraditionalLegalText(section.title),
      paragraphs: section.paragraphs.map(toTraditionalLegalText),
    })),
  }
}

export function getLegalDocument(
  kind: LegalDocumentKind,
  language: AppLanguage,
): LegalDocument {
  const source = kind === 'privacy'
    ? (language === 'en' ? PRIVACY_EN : PRIVACY_ZH)
    : (language === 'en' ? agreementEn() : agreementZh())
  return language === 'zh-Hant' ? toTraditional(source) : source
}
