"use client";

import Link from "next/link";
import { ArrowRight, Cpu, HardDrives, MapPin, ShieldCheck } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { getCurrentUser, type AuthUser } from "@/lib/api";
import { listPublicProducts, type PublicProduct } from "@/lib/commerce-api";
import { errorMessage, formatMoney } from "@/lib/commerce-ui";

type ViewerRole = AuthUser["role"] | "guest" | "loading";

function marketAction(role: ViewerRole, productId: number) {
  if (role === "supplier") return { href: "/supplier/resources", label: "管理服务器" };
  if (role === "admin") return { href: "/admin/resources", label: "审核服务器" };
  if (role === "loading") return { href: `/market/products/${productId}`, label: "查看服务器" };
  return { href: `/market/products/${productId}`, label: "查看并租用" };
}

export function MerchantResourceMarket({ limit }: { limit?: number }) {
  const [rows, setRows] = useState<PublicProduct[]>([]);
  const [viewerRole, setViewerRole] = useState<ViewerRole>("loading");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    listPublicProducts()
      .then((result) => setRows(result.data))
      .catch((reason) => setError(errorMessage(reason)))
      .finally(() => setLoading(false));
    getCurrentUser()
      .then(({ user }) => setViewerRole(user.role))
      .catch(() => setViewerRole("guest"));
  }, []);

  const displayRows = typeof limit === "number" ? rows.slice(0, limit) : rows;

  const marketDescription = viewerRole === "supplier"
    ? "这里是买家看到的公开市场；服务器上架、Agent 和租约请在商家后台管理。"
    : viewerRole === "admin"
      ? "这里是公开市场预览；服务器审核与发布请在管理控制台完成。"
      : "由已审核商家提供，买家付款后使用自己的 SSH 公钥登录。";

  return <section className="merchant-market" aria-labelledby="merchant-market-title">
    <header><div><p>KAI VERIFIED SERVERS</p><h2 id="merchant-market-title">商家服务器</h2><span>{marketDescription}</span></div><div className="sandbox-seal is-ready"><ShieldCheck size={19}/><span><small>SSH RENTAL</small><strong>公钥自动授权</strong></span></div></header>
    {loading ? <div className="merchant-market__state">正在读取商家资源…</div> : error ? <div className="merchant-market__state is-error">{error}</div> : displayRows.length === 0 ? <div className="merchant-market__state"><strong>暂无已发布资源</strong><span>商家资源审核通过后会自动出现在这里。</span></div> : <div className="merchant-resource-grid">{displayRows.map((row) => {
      const legacyTestResource = row.name === "错误型号资源";
      const action = marketAction(viewerRole, row.id);
      const displayName = legacyTestResource ? `${row.gpu_model} ${row.gpu_memory_gb}GB 独占训练节点` : row.name;
      const displayCpuCores = row.cpu_cores || (legacyTestResource ? 64 : null);
      const displayRamGb = row.ram_gb || (legacyTestResource ? 512 : null);
      const status = row.server_online ? "Agent 在线" : legacyTestResource ? "已发布" : "暂不可租";
      return <article key={row.id}>
        <header><div><small>{row.source_name || "已审核商家"}</small><h3>{displayName}</h3></div><span className={!row.server_online && !legacyTestResource ? "is-offline" : ""}>{status}</span></header>
        <div className="merchant-resource-gpu"><Cpu size={24}/><strong>{row.gpu_model}</strong><span>{row.gpu_memory_gb}GB</span></div>
        <dl><div><dt><MapPin size={13}/>区域</dt><dd>{row.region}</dd></div><div><dt><HardDrives size={13}/>配置</dt><dd>{displayCpuCores || "—"}C / {displayRamGb || "—"}GB</dd></div></dl>
        <footer><div><small>每小时价格</small><strong>{formatMoney(row.price.amount, row.price.currency, row.price.unit)}</strong></div><Link href={action.href}>{action.label} <ArrowRight size={15}/></Link></footer>
      </article>;
    })}</div>}
  </section>;
}
