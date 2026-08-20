"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Key, Plus, ShieldCheck, Trash } from "@phosphor-icons/react";
import { createSshKey, listSshKeys, revokeSshKey, type SshKey } from "@/lib/commerce-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

export function SshKeyWorkspace() {
  const [rows, setRows] = useState<SshKey[]>([]);
  const [name, setName] = useState("我的 Mac");
  const [publicKey, setPublicKey] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try { setRows((await listSshKeys()).data); } catch (reason) { setError(errorMessage(reason)); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await createSshKey({ name, public_key: publicKey });
      setPublicKey(""); setShowForm(false); await load();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }

  async function revoke(row: SshKey) {
    if (!window.confirm(`确认撤销“${row.name}”？有效租约使用中的公钥不能撤销。`)) return;
    setBusy(true); setError("");
    try { await revokeSshKey(row.id, row.version); await load(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(false); }
  }

  return <section className="workspace-page ssh-key-page"><header className="asset-control-head"><div><p>BUYER / SSH KEYS</p><h1>SSH 公钥</h1><span>只提交公钥。私钥始终保留在你的 Mac，不要上传给平台或商家。</span></div><button className="commerce-primary" onClick={() => setShowForm((value) => !value)}><Plus size={16}/>添加公钥</button></header>
    <div className="ssh-security-note"><ShieldCheck size={22}/><div><strong>公钥用于登录租用的服务器</strong><span>它不用于网站登录，也不用于商家或 Agent 身份认证。生产 Agent 使用独立 mTLS 证书。</span></div></div>
    {error && <div className="commerce-error">{error}</div>}
    {showForm && <form className="commerce-form ssh-key-form" onSubmit={(event) => void submit(event)}><header><span>OPENSSH PUBLIC KEY</span><h2>登记一把登录公钥</h2></header><label className="commerce-field"><span>设备名称</span><input required minLength={2} value={name} onChange={(event) => setName(event.target.value)}/></label><label className="commerce-field"><span>公钥内容</span><textarea required rows={5} value={publicKey} onChange={(event) => setPublicKey(event.target.value)} placeholder="ssh-ed25519 AAAA... your-device"/></label><footer><span>支持 Ed25519、RSA 和 ECDSA 公钥</span><button className="commerce-primary" disabled={busy}>{busy ? "保存中…" : "保存公钥"}</button></footer></form>}
    <div className="ssh-key-list">{rows.length ? rows.map((row) => <article key={row.id}><Key size={23}/><div><strong>{row.name}</strong><code>{row.fingerprint}</code><span>{row.algorithm} · 添加于 {formatDate(row.created_at)}{row.last_used_at ? ` · 最近使用 ${formatDate(row.last_used_at)}` : ""}</span></div><b className={`status-chip status-chip--${row.status === "active" ? "published" : "archived"}`}>{row.status === "active" ? "可用" : "已撤销"}</b>{row.status === "active" && <button disabled={busy} onClick={() => void revoke(row)}><Trash size={16}/>撤销</button>}</article>) : <div className="asset-empty"><Key size={30}/><strong>还没有 SSH 公钥</strong><span>可在 Mac 终端运行 ssh-keygen -t ed25519 创建。</span></div>}</div>
  </section>;
}
