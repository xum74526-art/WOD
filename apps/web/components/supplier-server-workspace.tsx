"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Check, Copy, Cube, DownloadSimple, HardDrives, Pulse, ShieldCheck, TerminalWindow } from "@phosphor-icons/react";
import { createAgentEnrollment, listSupplierServers, type AgentEnrollment, type SupplierServer } from "@/lib/commerce-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

type InstallTarget = "linux" | "windows" | "docker";

function formatBytes(value: number | null) {
  return value ? `${(value / 1024 / 1024).toFixed(1)} MB` : "待构建";
}

const hardwareLabels = {
  pending: "等待检测",
  verified: "配置已核验",
  mismatch: "配置不一致",
  stale: "检测已过期",
  unavailable: "无法检测",
} as const;

function HardwarePanel({ row }: { row: SupplierServer }) {
  const hardware = row.hardware;
  if (!hardware) return <section className="agent-hardware agent-hardware--pending"><header><strong>等待检测</strong></header><p>等待最新版 Agent 上报硬件清单。</p></section>;
  const inventory = hardware.inventory;
  const gpus = inventory.gpus || [];
  return <section className={`agent-hardware agent-hardware--${hardware.status}`}>
    <header><strong>{hardwareLabels[hardware.status]}</strong><span>{hardware.is_simulated ? "开发模拟数据" : `实测于 ${formatDate(hardware.observed_at)}`}</span></header>
    {hardware.status === "pending" ? <p>安装并运行最新版 Agent 后自动读取 CPU、内存、磁盘与 NVIDIA GPU。</p> : <>
      <dl>
        <div><dt>实测 GPU</dt><dd>{gpus.length ? gpus.map((gpu) => `${gpu.name} · ${(gpu.memory_total_mb / 1024).toFixed(1)} GB`).join(" / ") : "未检测到"}</dd></div>
        <div><dt>CPU</dt><dd>{inventory.cpu_logical_cores || 0} 线程 · {inventory.cpu_model || "未知"}</dd></div>
        <div><dt>内存 / 磁盘</dt><dd>{((inventory.memory_total_mb || 0) / 1024).toFixed(1)} GB / {inventory.disk_total_gb || 0} GB</dd></div>
        <div><dt>采集环境</dt><dd>{inventory.source || "—"} · {inventory.os_name || "—"}</dd></div>
      </dl>
      {hardware.mismatches.length > 0 && <ul>{hardware.mismatches.map((item) => <li key={item.field}>{item.message}</li>)}</ul>}
    </>}
  </section>;
}

function ServicePanel({ row }: { row: SupplierServer }) {
  const services = row.services;
  if (!services) return <section className="agent-hardware agent-hardware--pending"><header><strong>等待 SSH 自检</strong></header><p>等待 Agent 0.3.0 上报本机 SSH 服务状态。</p></section>;
  const ssh = services.checks.ssh;
  const healthy = services.status === "healthy";
  return <section className={`agent-hardware agent-hardware--${healthy ? "verified" : "unavailable"}`}>
    <header><strong>{healthy ? "SSH 服务可用" : services.status === "pending" ? "等待 SSH 自检" : "SSH 服务不可用"}</strong><span>{services.is_simulated ? "开发模拟" : `检测于 ${formatDate(services.observed_at)}`}</span></header>
    <p>{ssh ? `本机 127.0.0.1:${ssh.port} · ${ssh.reachable ? "端口可连接" : ssh.error || "连接失败"}` : "Agent 尚未上报 SSH 服务状态。"}</p>
  </section>;
}

function InstallPanel({ enrollment }: { enrollment: AgentEnrollment }) {
  const [target, setTarget] = useState<InstallTarget>("linux");
  const [copied, setCopied] = useState(false);
  const command = target === "linux" ? enrollment.linux_install_command : target === "windows" ? enrollment.windows_install_command : enrollment.docker_install_command;
  const inventoryCommand = target === "linux" ? "sudo kai-agent inventory && sudo kai-agent check" : target === "windows" ? '& "$env:ProgramFiles\\KAI Agent\\kai-agent.exe" inventory; & "$env:ProgramFiles\\KAI Agent\\kai-agent.exe" check' : "docker compose exec kai-agent sh -c 'kai-agent inventory && kai-agent check'";
  async function copyCommand() {
    await navigator.clipboard.writeText(command);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }
  return <section className="agent-install-panel">
    <header><div><small>ONE-TIME ENROLLMENT / {enrollment.server_no}</small><h2>安装 KAI Agent</h2><span>绑定码在 {formatDate(enrollment.expires_at)} 前有效，并且只能使用一次。</span></div><ShieldCheck size={24} /></header>
    <nav aria-label="Agent 安装方式">{(["linux", "windows", "docker"] as InstallTarget[]).map((item) => <button key={item} className={target === item ? "active" : ""} onClick={() => setTarget(item)}>{item === "linux" ? "Linux" : item === "windows" ? "Windows" : "Docker"}</button>)}</nav>
    <div className="agent-command"><code>{command}</code><button onClick={() => void copyCommand()}>{copied ? <Check size={16} /> : <Copy size={16} />}{copied ? "已复制" : "复制命令"}</button></div>
    <p>{target === "linux" && "在 root 或可使用 sudo 的 Linux 终端执行；安装器会创建 systemd 服务。"}{target === "windows" && "在管理员 PowerShell 执行；安装器会启用 OpenSSH 并创建开机任务。"}{target === "docker" && "先下载并解压 Docker 源包，在解压目录执行命令；容器默认把 SSH 映射到宿主机 2222 端口。"} 安装后可随时运行 <code>{inventoryCommand}</code> 查看实测配置。</p>
    <div className="agent-downloads">{enrollment.downloads.filter((item) => target === "docker" ? item.platform === "docker" : item.platform === target).map((item) => <a key={`${item.platform}-${item.arch}`} href={item.url} download>{item.platform === "docker" ? <Cube size={17} /> : <DownloadSimple size={17} />}<span><strong>{item.filename}</strong><small>{item.arch} · {formatBytes(item.size_bytes)}</small></span></a>)}</div>
    <footer>Agent 使用 Ed25519 设备签名、防重放随机数和主动出站连接；平台不会获得任意 Shell 权限。</footer>
  </section>;
}

export function SupplierServerWorkspace() {
  const [rows, setRows] = useState<SupplierServer[]>([]);
  const [enrollment, setEnrollment] = useState<AgentEnrollment | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => { try { setRows((await listSupplierServers()).data); } catch (reason) { setError(errorMessage(reason)); } }, []);
  useEffect(() => { void load(); const timer = window.setInterval(() => void load(), 15_000); return () => window.clearInterval(timer); }, [load]);
  async function bind(server: SupplierServer) {
    setBusyId(server.id); setError("");
    try { setEnrollment(await createAgentEnrollment(server.id)); await load(); } catch (reason) { setError(errorMessage(reason)); } finally { setBusyId(null); }
  }
  return <section className="workspace-page supplier-server-page">
    <header className="asset-control-head"><div><p>SUPPLIER / SERVERS</p><h1>服务器与 Agent</h1><span>下载 Agent、绑定真实服务器，并查看心跳和系统信息。</span></div><Link href="/supplier/resources"><HardDrives size={17} />登记服务器商品</Link></header>
    <div className="ssh-security-note"><ShieldCheck size={22}/><div><strong>支持 Linux、Windows 和 Docker</strong><span>每台服务器使用独立设备身份；Agent 只执行公钥授权、撤销和租户清理。</span></div></div>
    {error && <div className="commerce-error">{error}</div>}{enrollment && <InstallPanel enrollment={enrollment} />}
    <div className="server-registry">{rows.length ? rows.map((row) => <article key={row.id}><header><div><small>{row.server_no}</small><h2>{row.product_name}</h2><span>{row.public_host}:{row.ssh_port}</span></div><b className={`status-chip status-chip--${row.status === "online" ? "published" : "archived"}`}>{row.status === "online" ? "Agent 在线" : row.status === "registered" ? "等待绑定" : "Agent 离线"}</b></header><dl><div><dt>租户账号前缀</dt><dd>{row.ssh_username_prefix}</dd></div><div><dt>运行环境</dt><dd>{row.agent_platform ? `${row.agent_platform} / ${row.agent_arch}` : row.agent_mode === "local_simulator" ? "本机模拟器" : "待绑定"}</dd></div><div><dt>Agent 版本</dt><dd>{row.agent_version || "待接入"}</dd></div><div><dt>最近心跳</dt><dd>{formatDate(row.last_seen_at)}</dd></div><div><dt>设备主机名</dt><dd>{row.agent_hostname || "—"}</dd></div><div><dt>设备 ID</dt><dd className="agent-device-id">{row.agent_device_id ? `${row.agent_device_id.slice(0, 12)}…` : "—"}</dd></div></dl><HardwarePanel row={row}/><ServicePanel row={row}/><footer><span><Pulse size={16}/>商品状态：{row.resource_status}</span><button disabled={busyId === row.id} onClick={() => void bind(row)}><TerminalWindow size={15}/>{busyId === row.id ? "生成中…" : row.agent_device_id ? "重新绑定" : "安装 Agent"}</button></footer></article>) : <div className="asset-empty"><HardDrives size={30}/><strong>还没有服务器</strong><span>请先登记服务器商品，再回来下载安装 Agent。</span><Link href="/supplier/resources">登记服务器</Link></div>}</div>
  </section>;
}
