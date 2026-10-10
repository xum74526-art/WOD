from __future__ import annotations

from dataclasses import dataclass, replace
import re

from app.services.trade_mode import direct_trade_enabled, matchmaking_enabled


@dataclass(frozen=True)
class FaqAnswer:
    topic: str
    zh: str
    en: str
    keywords_zh: tuple[str, ...]
    keywords_en: tuple[str, ...]


FAQ_ANSWERS = (
    FaqAnswer(
        topic="account",
        zh="登录或注册可使用手机号；Kai 统一身份认证需在平台完成客户端配置后开放。忘记密码可在登录页进入“忘记密码”，按页面验证流程重设。若验证码无法使用，请创建工单并说明所用手机号后四位和报错现象，请勿发送密码。",
        en="You can sign in or register with a phone number. Kai unified sign-in becomes available after its client configuration is completed. Use Forgot Password on the sign-in page to reset a password. If verification fails, create a ticket with the last four digits of your phone number and the error; never send your password.",
        keywords_zh=("登录", "注册", "密码", "验证码", "手机号", "账号", "kai", "认证登录"),
        keywords_en=("login", "log in", "sign in", "register", "sign up", "password", "verification code", "phone", "account", "kai"),
    ),
    FaqAnswer(
        topic="purchase",
        zh="页面明确标记“可购买”的当前 KAI 报价可按整数 GPU 小时下单，并可选择购买使用或购买持有。订单和账户余额统一以人民币记账结算，系统冻结相应余额后进入“待平台人工交付 SSH”；繁体中文和英文界面仅按每日参考汇率换算显示港币或美元。确认交付后才生成对应资产；页面标记“仅供行情参考”的资源不能下单。",
        en="A current KAI quote explicitly marked Purchasable can be ordered for an integer number of GPU-hours in either Usage or Holding mode. Orders and wallet balances are recorded and settled in CNY. The server freezes the corresponding balance before manual SSH delivery; HKD or USD shown by other language settings is display-only and uses the daily reference rate. The matching asset is created only after delivery confirmation. Reference-only listings cannot be ordered.",
        keywords_zh=("购买", "下单", "订单", "取消", "ssh", "交付", "数量", "周期", "库存"),
        keywords_en=("buy", "purchase", "order", "cancel", "ssh", "delivery", "quantity", "term", "stock"),
    ),
    FaqAnswer(
        topic="compute",
        zh="算力行情仅使用 KAI Pricing 的当前人民币/GPU 小时报价，展示 GPU 型号、显存和地区报价样本。机型榜和区域价差只比较相同型号与显存规格，不会把不同 GPU 混算；报价样本不代表实时库存。平台商家自有资源仍按页面状态展示和购买。",
        en="The compute market uses only current KAI Pricing quotes in CNY/GPU-hour and shows quote observations by GPU model, memory variant, and region. Rankings and regional spreads compare the same GPU model and memory variant without mixing different GPUs; quote observations are not live inventory. First-party seller listings remain available according to their page status.",
        keywords_zh=("算力", "gpu", "显卡", "资源", "行情", "价格", "vast", "autodl", "图片", "显存", "机型"),
        keywords_en=("compute", "gpu", "resource", "market", "price", "vast", "autodl", "image", "memory", "model"),
    ),
    FaqAnswer(
        topic="hosting",
        zh="个人和商家都可以发起设备托管：个人设备托管前需完成实名认证；企业批量托管和商家运营功能仅对已认证商家开放。提交设备资料后会依次经过待审核、审核中、部署中和运行中等状态。",
        en="Both individuals and sellers can request device hosting. Individuals must complete identity verification first; business fleet hosting and seller operations require an approved seller account. Submitted devices move through pending review, under review, deployment, and running states.",
        keywords_zh=("托管", "设备", "部署", "运行中", "商家入驻", "机房"),
        keywords_en=("hosting", "host device", "device", "deployment", "running", "seller onboarding", "data center"),
    ),
    FaqAnswer(
        topic="verification",
        zh="实名认证需要提交本人真实姓名、身份证信息及页面要求的证件图片。资料会进入人工审核，不会自动通过。请勿在客服消息中发送完整身份证号或证件照片；若审核异常，只需创建工单并描述页面状态。",
        en="Identity verification requires your legal name, identity details, and the document images requested on the verification page. It is reviewed manually and is never auto-approved. Do not send a full ID number or document image in support chat; create a ticket describing the page status instead.",
        keywords_zh=("实名认证", "身份认证", "身份证", "审核", "认证失败", "认证中"),
        keywords_en=("identity verification", "real-name", "id card", "verification review", "verification failed"),
    ),
    FaqAnswer(
        topic="payment",
        zh="充值渠道是否可用以充值页面和服务端实时状态为准。支付完成后仍以服务端验签回调或主动查单结果入账，页面跳转本身不代表充值成功。算力订单和账户余额统一以人民币记账结算；繁体中文和英文界面的港币、美元金额仅为每日参考汇率换算展示。平台不会要求向个人银行卡、微信或支付宝转账。",
        en="Recharge availability follows the live status shown on the recharge page. A recharge is credited only after a server-verified callback or provider query; returning from checkout does not itself prove payment. Compute orders and wallet balances are recorded and settled in CNY. HKD or USD amounts shown by other language settings are display-only conversions using the daily reference rate. The platform never asks you to transfer money to a personal bank card, WeChat, or Alipay account.",
        keywords_zh=("支付", "充值", "退款", "扣款", "付款", "冻结", "余额", "卡时"),
        keywords_en=("payment", "pay", "recharge", "top up", "refund", "debit", "frozen", "balance", "ch"),
    ),
    FaqAnswer(
        topic="withdrawal",
        zh="银行卡自动代付接口尚未接入。提现需先完成实名认证、登记本人银行卡并提交申请，由财务人工审核和打款；只有管理员记录打款凭证后，订单才会标记完成。请勿相信绕过平台审核的代提现要求。",
        en="Automated bank payouts are not connected. A withdrawal requires identity review, registration of a bank card in your name, and a submitted request. Finance reviews and pays it manually, and the order is marked complete only after an administrator records payment evidence. Do not accept any request that bypasses the platform review flow.",
        keywords_zh=("提现", "银行卡", "到账", "出金", "代付"),
        keywords_en=("withdraw", "withdrawal", "bank card", "payout", "cash out", "deposit arrived"),
    ),
    FaqAnswer(
        topic="notification",
        zh="站内消息可在“我的－消息通知”查看并标记已读。订单、设备告警和收益提醒的开关只有在对应服务端事件通道启用后才可使用；未配置的通道会明确显示“暂不可用”，不会假装已推送。",
        en="In-app messages are available under Profile > Notifications and can be marked as read. Order, device-alert, and revenue switches only work after their server event channels are enabled. Unconfigured channels are shown as unavailable and never pretend a push was sent.",
        keywords_zh=("通知", "消息", "提醒", "推送", "设备告警", "订单通知", "收益提醒"),
        keywords_en=("notification", "message", "reminder", "push", "device alert", "order alert", "revenue alert"),
    ),
)


MATCHMAKING_FAQ_COPY = {
    "purchase": {
        "zh": "当前版本不在 App 内直接下单、扣减账户余额或收款。您可以在资源详情提交需求，由已认证商家在需求市场报价；选定合适方案后仅提交合作意向，由平台工作人员继续协调交付。双方联系方式和 SSH 等敏感信息不会在报价阶段公开。",
        "en": "This version does not place paid orders, debit the wallet balance, or collect payment in the app. Submit a requirement from a resource page and verified sellers can quote in the request market. Choosing a suitable proposal records a cooperation intention for platform coordination only; contact details and SSH credentials remain private during quoting.",
    },
    "compute": {
        "zh": "算力行情继续展示 KAI Pricing 的人民币/GPU 小时报价、曲线、GPU 型号、显存和地区样本。报价样本用于行情与询价参考，不代表实时库存或成交价；KAI 自营和商家资源会明确区分，当前均通过“提交需求”进入撮合流程。",
        "en": "The compute market continues to show KAI Pricing observations, charts, GPU models, memory variants, and regions in CNY/GPU-hour. Observations are references for market information and inquiries, not live inventory or a transaction price. KAI-operated and seller resources are identified separately and currently use the Submit Requirement flow.",
    },
    "payment": {
        "zh": "当前撮合版本未开放 App 内充值、支付、余额扣减或退款入口，也不会要求您向个人银行卡、微信或支付宝转账。资源报价与合作意向不等于已付款或已成交，后续安排以平台工作人员核验和确认的方案为准。",
        "en": "The current matchmaking version does not offer in-app recharge, payment, wallet debit, or refund actions and will never ask you to transfer money to a personal bank card, WeChat, or Alipay account. A quote or cooperation intention is not proof of payment or a completed transaction; follow only arrangements verified by platform staff.",
    },
    "withdrawal": {
        "zh": "当前撮合版本未开放提现申请和银行卡登记入口。历史钱包与流水仍可查看，但赠送余额及邀请奖励仅用于平台内符合条件的消费，不可提现。后续资质和资金通道完备后，相关能力将由独立服务开关启用。",
        "en": "The current matchmaking version does not accept withdrawal requests or new bank-card registrations. Historical wallet records remain readable, while promotional balance and invitation rewards are for eligible in-platform use only and are not withdrawable. These capabilities can be enabled separately after the required qualifications and payment rails are ready.",
    },
}


HISTORY_ONLY_FAQ_COPY = {
    "purchase": {
        "zh": "当前暂未开放需求撮合或 App 内交易，行情、曲线和历史记录仍可查看。请以页面实时状态为准。",
        "en": "Requirement matching and in-app transactions are currently unavailable. Market data, charts, and historical records remain readable; follow the live status shown on each page.",
    },
    "payment": {
        "zh": "当前未开放充值、支付、余额扣减或退款入口，历史充值订单和钱包流水仍可查看。",
        "en": "Recharge, payment, wallet debit, and refund actions are currently unavailable. Historical recharge orders and wallet ledger records remain readable.",
    },
    "withdrawal": {
        "zh": "当前未开放提现申请，历史提现记录仍可查看。",
        "en": "New withdrawal requests are currently unavailable. Historical withdrawal records remain readable.",
    },
}


def _runtime_answer(answer: FaqAnswer) -> FaqAnswer:
    """Keep support copy aligned with the effective server commerce mode."""

    if direct_trade_enabled():
        return answer
    copy = MATCHMAKING_FAQ_COPY if matchmaking_enabled() else HISTORY_ONLY_FAQ_COPY
    override = copy.get(answer.topic)
    if not override:
        return answer
    return replace(answer, zh=override["zh"], en=override["en"])


HUMAN_KEYWORDS_ZH = ("转人工", "人工客服", "联系人工", "人工工单", "投诉")
HUMAN_KEYWORDS_EN = ("human support", "human agent", "contact support", "support ticket", "complaint")


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def match_faq(message: str, lang: str) -> FaqAnswer | None:
    text = _normalized(message)
    candidates: list[tuple[int, FaqAnswer]] = []
    for answer in FAQ_ANSWERS:
        keywords = answer.keywords_en if lang == "en" else answer.keywords_zh
        score = sum(max(1, len(keyword)) for keyword in keywords if keyword.lower() in text)
        if score:
            candidates.append((score, answer))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return _runtime_answer(candidates[0][1])


def asks_for_human(message: str, lang: str) -> bool:
    text = _normalized(message)
    keywords = HUMAN_KEYWORDS_EN if lang == "en" else HUMAN_KEYWORDS_ZH
    return any(keyword in text for keyword in keywords)


def unknown_reply(lang: str) -> str:
    if lang == "en":
        return (
            "I could not find a reliable self-service answer for that question. "
            "You can create a support ticket below. An administrator can claim it and reply in this conversation; "
            "no fixed response SLA is promised."
        )
    return (
        "我暂时没有找到可靠的自助答案。您可以在下方创建真实工单。"
        "管理员认领后会在本会话回复；当前不承诺固定回复时限。"
    )


def human_request_reply(lang: str) -> str:
    if lang == "en":
        return (
            "Create a support ticket below. It will remain Pending assignment until a real administrator claims it, "
            "then the reply will appear in this conversation and your inbox."
        )
    return "您可以在下方创建真实工单；管理员认领后会在本会话和消息中心回复，认领前状态会如实显示为“待分配”。"


def localized_builtin_reply(topic: str | None, lang: str) -> str | None:
    """Return current-language copy for persisted deterministic support replies."""

    if topic == "human_support":
        return human_request_reply(lang)
    if topic == "other":
        return unknown_reply(lang)
    answer = next((item for item in FAQ_ANSWERS if item.topic == topic), None)
    if not answer:
        return None
    localized = _runtime_answer(answer)
    return localized.en if lang == "en" else localized.zh
