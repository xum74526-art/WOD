"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Clock, Cpu, MapPin, ShieldCheck } from "@phosphor-icons/react";
import { getPublicRequest, type BuyRequest } from "@/lib/commerce-api";
import { errorMessage, formatDate, formatMoney, requestStatusLabel } from "@/lib/commerce-ui";

export function PublicRequestDetail({ requestNo }: { requestNo: string }) {
  const [row, setRow] = useState<BuyRequest | null>(null); const [error, setError] = useState("");
  useEffect(() => { getPublicRequest(requestNo).then(setRow).catch((reason) => setError(errorMessage(reason))); }, [requestNo]);
  if (error) return <div className="commerce-error">{error}<Link href="/requests">返回市场</Link></div>;
  if (!row) return <div className="commerce-loading">正在读取采购任务…</div>;
  return <article className="request-dossier">
    <Link className="dossier-back" href="/requests"><ArrowLeft size={14} />返回公开求购</Link>
    <header><div><p>{row.request_no}</p><h1>{row.title}</h1><span className={`status-chip status-chip--${row.status}`}>{requestStatusLabel[row.status]}</span></div><aside><small>预算上限</small><strong>{formatMoney(row.budget.amount, row.budget.currency, row.budget.unit)}</strong><span><Clock size={14} />{formatDate(row.quote_deadline_at)} 截止</span></aside></header>
    <section className="dossier-facts"><div><Cpu size={19} /><small>GPU 配置</small><strong>{row.gpu_model} × {row.gpu_quantity}</strong><span>{row.min_gpu_memory_gb ? `最低显存 ${row.min_gpu_memory_gb} GB` : "显存不限"}</span></div><div><MapPin size={19} /><small>区域 / 交付</small><strong>{row.region_codes.join(" / ") || "地区不限"}</strong><span>{row.delivery_mode === "remote" ? "远程交付" : "协商交付"}</span></div><div><Clock size={19} /><small>预计时长</small><strong>{row.expected_duration_hours ? `${row.expected_duration_hours} 小时` : "待协商"}</strong><span>{row.expected_start_at ? `${formatDate(row.expected_start_at)} 开始` : "开始时间待协商"}</span></div></section>
    <section className="dossier-body"><div><p className="hero-eyebrow">DELIVERY BRIEF</p><h2>部署与服务要求</h2><p>{row.requirements || "买家未补充其他要求。"}</p>{row.cloud_details && <dl><div><dt>CPU</dt><dd>{row.cloud_details.min_cpu_cores ? `≥ ${row.cloud_details.min_cpu_cores} 核` : "不限"}</dd></div><div><dt>内存</dt><dd>{row.cloud_details.min_ram_gb ? `≥ ${row.cloud_details.min_ram_gb} GB` : "不限"}</dd></div><div><dt>公网 IP</dt><dd>{row.cloud_details.public_ip_required ? "需要" : "不要求"}</dd></div></dl>}</div><aside><ShieldCheck size={22} /><strong>商家报价入口</strong><p>只有审核通过的商家可以查看报价工作区并提交报价。公开页面不提供买家联系方式。</p><Link className="primary-link" href="/supplier/requests">进入商家报价台</Link></aside></section>
  </article>;
}
