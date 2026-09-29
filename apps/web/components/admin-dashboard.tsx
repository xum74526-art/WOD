"use client";

import Link from "next/link";
import { ArrowRight, Bank, Bell, ClipboardText, Gavel, HardDrives, IdentificationCard, Receipt, Storefront, UsersThree } from "@phosphor-icons/react/dist/ssr";
import { useI18n } from "@/components/locale-root";

const queues = [
  { eyebrow: "SERVICE REQUESTS", titleKey: "admin.dashboard.requests.title", title: "需求管理", descriptionKey: "admin.dashboard.requests.description", description: "查看用户提交的算力需求、指定商家与联系方式，供运营人员线下跟进。", href: "/admin/requests", labelKey: "admin.dashboard.requests.action", label: "查看需求", icon: ClipboardText },
  { eyebrow: "DEVICE HOSTING", titleKey: "admin.dashboard.onboardings.title", title: "设备托管", descriptionKey: "admin.dashboard.onboardings.description", description: "受理设备托管申请，记录联系、通过或驳回结论，并把处理结果同步给用户。", href: "/admin/onboardings", labelKey: "admin.dashboard.onboardings.action", label: "进入托管队列", icon: HardDrives },
  { eyebrow: "PLATFORM DATA", titleKey: "admin.dashboard.data.title", title: "端口数据", descriptionKey: "admin.dashboard.data.description", description: "统一查看 Web、iOS、Android、管理端及历史来源的用户、订单与充值数据。", href: "/admin/data", labelKey: "admin.dashboard.data.action", label: "查看端口数据", icon: UsersThree },
  { eyebrow: "IDENTITY", titleKey: "admin.dashboard.kyc.title", title: "实名认证", descriptionKey: "admin.dashboard.kyc.description", description: "核验个人或企业主体，结论控制商家准入与提现。", href: "/admin/kyc", labelKey: "admin.dashboard.kyc.action", label: "进入实名队列", icon: IdentificationCard },
  { eyebrow: "MERCHANT ADMISSION", titleKey: "admin.dashboard.suppliers.title", title: "商家入驻审核", descriptionKey: "admin.dashboard.suppliers.description", description: "单独审核商家入驻资料；只有已完成实名认证的申请人才能通过。", href: "/admin/suppliers", labelKey: "admin.dashboard.suppliers.action", label: "进入入驻队列", icon: Storefront },
  { eyebrow: "ORDER DISPUTES", titleKey: "admin.dashboard.disputes.title", title: "订单争议", descriptionKey: "admin.dashboard.disputes.description", description: "核对商品快照与安全交付证据，执行退回买家冻结金额或放行商家结算。", href: "/admin/disputes", labelKey: "admin.dashboard.disputes.action", label: "进入争议队列", icon: Gavel },
  { eyebrow: "MESSAGE CENTER", titleKey: "admin.dashboard.notifications.title", title: "消息发布", descriptionKey: "admin.dashboard.notifications.description", description: "向所有有效账号发布站内公告，支持安全跳转并保留发布审计记录。", href: "/admin/notifications", labelKey: "admin.dashboard.notifications.action", label: "发布站内消息", icon: Bell },
  { eyebrow: "PAYMENT OPERATIONS", titleKey: "admin.dashboard.payments.title", title: "充值与人民币退款", descriptionKey: "admin.dashboard.payments.description", description: "复核七相充值、查看支付事件，并处理全额人民币原支付渠道退款。", href: "/admin/refunds", labelKey: "admin.dashboard.payments.action", label: "进入支付运营", icon: Receipt },
  { eyebrow: "BANK CARDS", titleKey: "admin.dashboard.cards.title", title: "银行卡复核", descriptionKey: "admin.dashboard.cards.description", description: "核对用户登记的持卡人、银行和预留手机号，不冒充银行验卡。", href: "/admin/bank-cards", labelKey: "admin.dashboard.cards.action", label: "进入银行卡队列", icon: Bank },
  { eyebrow: "PAYOUT", titleKey: "admin.dashboard.withdrawals.title", title: "提现结算", descriptionKey: "admin.dashboard.withdrawals.description", description: "审核商家提现，完成线下转账后登记银行流水。", href: "/admin/withdrawals", labelKey: "admin.dashboard.withdrawals.action", label: "进入结算队列", icon: Bank },
] as const;

export function AdminDashboard() {
  const { t } = useI18n();
  return <section className="workspace-page admin-overview">
    <div className="workspace-page__head"><p>PLATFORM / CONTROL PLANE</p><h1>{t("admin.dashboard.title", "平台运营控制台")}</h1><span>{t("admin.dashboard.description", "这里只处理平台级审核与仲裁，不混入买家采购或商家经营功能。")}</span></div>
    <div className="admin-authority-line"><span>ROLE</span><strong>ADMINISTRATOR</strong><i /><span>SESSION</span><strong>ACCESS CONTROLLED</strong><i /><span>DATA</span><strong>CANONICAL API</strong></div>
    <div className="role-overview-grid">{queues.map(({ eyebrow, titleKey, title, descriptionKey, description, href, labelKey, label, icon: Icon }) => <Link href={href} key={href}>
      <header><Icon size={22} /><small>{eyebrow}</small></header><h2>{t(titleKey, title)}</h2><p>{t(descriptionKey, description)}</p><footer>{t(labelKey, label)}<ArrowRight size={16} /></footer>
    </Link>)}</div>
    <div className="workspace-service-note">{t("admin.dashboard.audit", "管理员统一处理需求、用户、订单、充值、实名、银行卡和提现；敏感操作均保留审计记录。")}</div>
  </section>;
}
