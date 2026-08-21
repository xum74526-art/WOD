import Link from "next/link";
import { ArrowRight, Bank, IdentificationCard } from "@phosphor-icons/react/dist/ssr";

const queues = [
  { eyebrow: "IDENTITY", title: "实名认证", description: "核验个人或企业主体，结论控制商家准入与提现。", href: "/admin/kyc", label: "进入实名队列", icon: IdentificationCard },
  { eyebrow: "BANK CARDS", title: "银行卡复核", description: "核对用户登记的持卡人、银行和预留手机号，不冒充银行验卡。", href: "/admin/bank-cards", label: "进入银行卡队列", icon: Bank },
  { eyebrow: "PAYOUT", title: "提现结算", description: "审核商家提现，完成线下转账后登记银行流水。", href: "/admin/withdrawals", label: "进入结算队列", icon: Bank },
] as const;

export function AdminDashboard() {
  return <section className="workspace-page admin-overview">
    <div className="workspace-page__head"><p>PLATFORM / CONTROL PLANE</p><h1>平台运营控制台</h1><span>这里只处理平台级审核与仲裁，不混入买家采购或商家经营功能。</span></div>
    <div className="admin-authority-line"><span>ROLE</span><strong>ADMINISTRATOR</strong><i /><span>SECURITY</span><strong>SERVER VERIFIED</strong><i /><span>CHANGES</span><strong>AUDITED</strong></div>
    <div className="role-overview-grid">{queues.map(({ eyebrow, title, description, href, label, icon: Icon }) => <Link href={href} key={href}>
      <header><Icon size={22} /><small>{eyebrow}</small></header><h2>{title}</h2><p>{description}</p><footer>{label}<ArrowRight size={16} /></footer>
    </Link>)}</div>
    <div className="workspace-service-note">当前只展示手机端财务后端已正式提供的审核能力；未接入手机端数据源的旧管理模块已从导航移除。</div>
  </section>;
}
