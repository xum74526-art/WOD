"use client";

import { useCallback, useEffect, useState } from "react";
import { Copy, Key, Plus, Prohibit } from "@phosphor-icons/react";
import { createApiKey, listApiKeys, revokeApiKey, type ApiCredential } from "@/lib/internal-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

export function ApiKeyWorkspace() {
  const [rows, setRows] = useState<ApiCredential[]>([]); const [secret, setSecret] = useState(""); const [error, setError] = useState("");
  const load = useCallback(async () => { try { setRows(await listApiKeys()); } catch (reason) { setError(errorMessage(reason)); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function create() { const name = window.prompt("密钥名称", "自动化读取"); if (!name?.trim()) return; try { const row = await createApiKey({ name: name.trim(), scopes: ["market:read", "orders:read"], expires_in_days: 90 }); setSecret(row.secret || ""); await load(); } catch (reason) { setError(errorMessage(reason)); } }
  async function revoke(id: number) { try { await revokeApiKey(id); await load(); } catch (reason) { setError(errorMessage(reason)); } }
  return <section className="workspace-page internal-workspace"><div className="workspace-page__head"><p>ACCOUNT / DEVELOPER</p><h1>API Key</h1><span>为自动化程序创建最小权限凭据；密钥明文只显示一次。</span></div>
    <div className="internal-toolbar"><strong>{rows.filter((row) => row.status === "active").length} 个有效密钥</strong><button onClick={() => void create()}><Plus size={16}/>创建密钥</button></div>{error && <div className="commerce-error">{error}</div>}
    {secret && <div className="secret-once"><Key size={22}/><div><strong>立即保存这段密钥</strong><code>{secret}</code><span>关闭后无法再次查看。</span></div><button onClick={() => void navigator.clipboard.writeText(secret)}><Copy size={16}/>复制</button></div>}
    <div className="key-list">{rows.length === 0 ? <div className="internal-empty"><Key size={30}/><strong>还没有 API Key</strong><span>创建后只保存不可逆哈希，不保存明文。</span></div> : rows.map((row) => <article key={row.id}><div><span className={`status-dot ${row.status}`}/><strong>{row.name}</strong><code>{row.key_prefix}••••••</code></div><p>{row.scopes.join(" · ")}</p><time>创建 {formatDate(row.created_at)}{row.expires_at ? ` · 到期 ${formatDate(row.expires_at)}` : ""}</time>{row.status === "active" && <button onClick={() => { if (window.confirm("吊销后不可恢复，确定继续？")) void revoke(row.id); }}><Prohibit size={15}/>吊销</button>}</article>)}</div>
  </section>;
}
