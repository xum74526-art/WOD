import Link from "next/link";
import { ArrowRight, Bank, ChatCircleText, Cube, Gavel, IdentificationCard, ShieldCheck } from "@phosphor-icons/react/dist/ssr";

const queues = [
  { eyebrow: "IDENTITY", title: "实名认证", description: "核验个人或企业主体，结论控制商家准入与提现。", href: "/admin/kyc", label: "进入实名队列", icon: IdentificationCard },
  { eyebrow: "ACCESS", title: "商家准入", description: "核验主体和联系人，通过后才授予商家角色。", href: "/admin/suppliers", label: "进入准入队列", icon: ShieldCheck },
  { eyebrow: "SUPPLY", title: "资源审核", description: "检查 GPU 规格、价格与容量，决定资源能否发布。", href: "/admin/resources", label: "进入资源队列", icon: Cube },
  { eyebrow: "PAYOUT", title: "提现结算", description: "审核商家提现，完成线下转账后登记银行流水。", href: "/admin/withdrawals", label: "进入结算队列", icon: Bank },
  { eyebrow: "RESOLUTION", title: "争议仲裁", description: "处理真实订单争议，结论会通知交易双方。", href: "/admin/disputes", label: "进入争议队列", icon: Gavel },
  { eyebrow: "CONTENT", title: "内容治理", description: "处理举报、隐藏、恢复和人工复核中的留言。", href: "/admin/moderation", label: "进入治理队列", icon: ChatCircleText },
] as const;

export function AdminDashboard() {
  return <section className="workspace-page admin-overview">
    <div className="workspace-page__head"><p>PLATFORM / CONTROL PLANE</p><h1>平台运营控制台</h1><span>这里只处理平台级审核与仲裁，不混入买家采购或商家经营功能。</span></div>
    <div className="admin-authority-line"><span>ROLE</span><strong>ADMINISTRATOR</strong><i /><span>SECURITY</span><strong>SERVER VERIFIED</strong><i /><span>CHANGES</span><strong>AUDITED</strong></div>
    <div className="role-overview-grid">{queues.map(({ eyebrow, title, description, href, label, icon: Icon }) => <Link href={href} key={href}>
      <header><Icon size={22} /><small>{eyebrow}</small></header><h2>{title}</h2><p>{description}</p><footer>{label}<ArrowRight size={16} /></footer>
    </Link>)}</div>
    <div className="workspace-service-note">实名认证与商家准入采用平台人工审核；提现采用人工审核与线下银行转账，并保留完整状态记录。</div>
  </section>;
}
