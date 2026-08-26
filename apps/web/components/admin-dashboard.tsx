import Link from "next/link";
import { ArrowRight, Bank, Gavel, IdentificationCard, Storefront, UsersThree } from "@phosphor-icons/react/dist/ssr";

const queues = [
  { eyebrow: "PLATFORM DATA", title: "端口数据", description: "统一查看 Web、iOS、Android、管理端及历史来源的用户、订单与充值数据。", href: "/admin/data", label: "查看端口数据", icon: UsersThree },
  { eyebrow: "IDENTITY", title: "实名认证", description: "核验个人或企业主体，结论控制商家准入与提现。", href: "/admin/kyc", label: "进入实名队列", icon: IdentificationCard },
  { eyebrow: "MERCHANT ADMISSION", title: "商家入驻审核", description: "单独审核商家入驻资料；只有已完成实名认证的申请人才能通过。", href: "/admin/suppliers", label: "进入入驻队列", icon: Storefront },
  { eyebrow: "ORDER DISPUTES", title: "订单争议", description: "核对商品快照与安全交付证据，执行退回买家卡时或放行商家结算。", href: "/admin/disputes", label: "进入争议队列", icon: Gavel },
  { eyebrow: "BANK CARDS", title: "银行卡复核", description: "核对用户登记的持卡人、银行和预留手机号，不冒充银行验卡。", href: "/admin/bank-cards", label: "进入银行卡队列", icon: Bank },
  { eyebrow: "PAYOUT", title: "提现结算", description: "审核商家提现，完成线下转账后登记银行流水。", href: "/admin/withdrawals", label: "进入结算队列", icon: Bank },
] as const;

export function AdminDashboard() {
  return <section className="workspace-page admin-overview">
    <div className="workspace-page__head"><p>PLATFORM / CONTROL PLANE</p><h1>平台运营控制台</h1><span>这里只处理平台级审核与仲裁，不混入买家采购或商家经营功能。</span></div>
    <div className="admin-authority-line"><span>ROLE</span><strong>ADMINISTRATOR</strong><i /><span>SESSION</span><strong>ACCESS CONTROLLED</strong><i /><span>DATA</span><strong>CANONICAL API</strong></div>
    <div className="role-overview-grid">{queues.map(({ eyebrow, title, description, href, label, icon: Icon }) => <Link href={href} key={href}>
      <header><Icon size={22} /><small>{eyebrow}</small></header><h2>{title}</h2><p>{description}</p><footer>{label}<ArrowRight size={16} /></footer>
    </Link>)}</div>
    <div className="workspace-service-note">用户、订单和充值按端口来源统一审计；实名、银行卡和提现仍需独立财务管理员权限。</div>
  </section>;
}
