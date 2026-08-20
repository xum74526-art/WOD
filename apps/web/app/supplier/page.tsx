import Link from "next/link";
import { ArrowRight, Cube, Gear, HardDrives, Key } from "@phosphor-icons/react/dist/ssr";
import { ProductShell } from "@/components/product-shell";

const operations = [
  { eyebrow: "LISTING", title: "登记服务器商品", description: "填写服务器规格、SSH 入口与小时价格，提交平台审核。", href: "/supplier/resources", icon: Cube },
  { eyebrow: "AGENT", title: "服务器与 Agent", description: "检查 Agent 在线状态；生产环境使用独立 mTLS 设备证书。", href: "/supplier/servers", icon: HardDrives },
  { eyebrow: "LEASES", title: "查看服务器租约", description: "查看租期、公钥指纹以及授权、撤销和宽限状态。", href: "/supplier/leases", icon: Key },
  { eyebrow: "PROFILE", title: "维护商家资料", description: "更新服务名称、联系人、服务地区和业务说明。", href: "/supplier/settings", icon: Gear },
] as const;

export default function SupplierDashboardPage() {
  return <ProductShell variant="supplier"><section className="workspace-page supplier-overview"><div className="workspace-page__head"><p>SUPPLIER / OPERATIONS</p><h1>服务器商家后台</h1><span>商家只负责提供服务器并保持 Agent 在线，平台负责订单、租期和公钥授权。</span></div>
    <div className="supplier-operation-line"><span>工作顺序</span><strong>登记服务器</strong><i>→</i><strong>管理员审核</strong><i>→</i><strong>买家购买</strong><i>→</i><strong>Agent 自动授权</strong></div>
    <div className="role-overview-grid">{operations.map(({ eyebrow, title, description, href, icon: Icon }) => <Link href={href} key={href}><header><Icon size={22}/><small>{eyebrow}</small></header><h2>{title}</h2><p>{description}</p><footer>进入处理 <ArrowRight size={16}/></footer></Link>)}</div>
    <div className="workspace-service-note">支付仍为可替换占位；SSH 公钥租约、2 小时续费宽限期和 Agent 命令框架已经接入。</div>
  </section></ProductShell>;
}
