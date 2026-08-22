from __future__ import annotations

from dataclasses import dataclass
import re


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
        zh="封闭测试中，页面明确标记“可购买”的当前有效报价可生成测试订单，并按周期和数量全额扣除站内测试卡时，随后进入“待平台人工交付 SSH”。外部报价订单不代表已在 Vast.ai、AutoDL 完成购买，也不涉及法币支付；页面标记“仅供行情参考”的资源仍不能下单。",
        en="During closed testing, a current quote explicitly marked Purchasable can create a test order. The full test-CH amount for its term and quantity is deducted, then the order waits for manual SSH delivery by the platform. An external-quote test order does not mean WOD purchased on Vast.ai or AutoDL and does not involve fiat payment. Reference-only listings still cannot be ordered.",
        keywords_zh=("购买", "下单", "订单", "取消", "ssh", "交付", "数量", "周期", "库存"),
        keywords_en=("buy", "purchase", "order", "cancel", "ssh", "delivery", "quantity", "term", "stock"),
    ),
    FaqAnswer(
        topic="compute",
        zh="算力市场展示 GPU 型号、显存、地区、库存和每 GPU 小时卡时价格。WOD 商家资源可按页面状态购买；Vast.ai、AutoDL 数据来自各自公开或授权接口，仅供行情参考。若图片未加载，可刷新页面或切换网络，资源详情和报价状态不受占位图影响。",
        en="The compute market shows GPU model, memory, region, availability, and CH per GPU-hour. WOD seller listings can be purchased when their page says they are available. Vast.ai and AutoDL data comes from public or authorized interfaces and is for market reference only. If an image does not load, refresh or switch networks; the placeholder does not change the listing or quote status.",
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
        zh="当前封闭测试尚未接入真实充值、法币支付和退款通道。页面标记可购买的测试订单会全额扣除站内测试卡时并进入“待平台人工交付 SSH”，但不会发生银行卡、微信、支付宝或其他法币资金划转。请勿向任何个人账户转账。",
        en="Real recharge, fiat-payment, and refund channels are not connected during closed testing. A test order marked Purchasable deducts the full in-app test-CH amount and then waits for manual SSH delivery by the platform, but no bank-card, WeChat Pay, Alipay, or other fiat transfer occurs. Never transfer money to a personal account.",
        keywords_zh=("支付", "充值", "退款", "扣款", "付款", "冻结", "余额", "卡时"),
        keywords_en=("payment", "pay", "recharge", "top up", "refund", "debit", "frozen", "balance", "ch"),
    ),
    FaqAnswer(
        topic="withdrawal",
        zh="当前封闭测试尚未接入真实提现和银行卡代付接口，因此不能产生真实到账。提现开放后会要求实名认证、绑定本人银行卡并由服务端返回渠道流水号；在此之前请勿提交或相信任何线下代提现要求。",
        en="Real withdrawal and bank payout services are not connected during closed testing, so no real payout can occur. When enabled, withdrawal will require identity verification, a bank card in your name, and a provider transaction ID returned by the server. Do not accept any offline withdrawal request.",
        keywords_zh=("提现", "银行卡", "到账", "出金", "代付"),
        keywords_en=("withdraw", "withdrawal", "bank card", "payout", "cash out", "deposit arrived"),
    ),
    FaqAnswer(
        topic="notification",
        zh="站内消息可在“我的－消息通知”查看并标记已读。订单、设备告警和收益提醒的开关只有在对应服务端事件通道启用后才可使用；封闭测试未配置的通道会明确显示“暂不可用”，不会假装已推送。",
        en="In-app messages are available under Profile > Notifications and can be marked as read. Order, device-alert, and revenue switches only work after their server event channels are enabled. Channels not configured during closed testing are shown as unavailable and never pretend a push was sent.",
        keywords_zh=("通知", "消息", "提醒", "推送", "设备告警", "订单通知", "收益提醒"),
        keywords_en=("notification", "message", "reminder", "push", "device alert", "order alert", "revenue alert"),
    ),
)


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
    return candidates[0][1]


def asks_for_human(message: str, lang: str) -> bool:
    text = _normalized(message)
    keywords = HUMAN_KEYWORDS_EN if lang == "en" else HUMAN_KEYWORDS_ZH
    return any(keyword in text for keyword in keywords)


def unknown_reply(lang: str) -> str:
    if lang == "en":
        return (
            "I could not find a reliable self-service answer for that question. "
            "You can create a real support ticket below. No human agent or response SLA is configured yet, "
            "so the ticket will be saved as Pending assignment until an operator channel is connected."
        )
    return (
        "我暂时没有找到可靠的自助答案。您可以在下方创建真实工单。"
        "目前尚未配置人工坐席和回复时限，工单会如实保存为“待分配”，待人工服务通道接入后处理。"
    )


def human_request_reply(lang: str) -> str:
    if lang == "en":
        return (
            "Human agents are not connected yet. You can still create a real support ticket below; "
            "it will be stored as Pending assignment, without claiming that an agent has accepted it."
        )
    return "人工坐席尚未接入。您仍可在下方创建真实工单；工单将保存为“待分配”，不会虚构已接通或已受理。"
