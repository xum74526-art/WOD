"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { Camera, Key, ShieldCheck, Storefront, UserCircle } from "@phosphor-icons/react";
import {
  changeMobilePassword,
  getMobileUserProfile,
  mobileAvatarUrl,
  switchMobileRole,
  updateMobileUserProfile,
  uploadMobileAvatar,
  type MobileUserProfile,
} from "@/lib/mobile-business-api";
import { errorMessage } from "@/lib/commerce-ui";
import {
  exchangeKaiBindingTicket,
  getKaiBindingStatus,
  startKaiBinding,
  type KaiBindingStatus,
} from "@/lib/api";

const roleLabel: Record<string, string> = { personal: "个人用户", supplier: "商家", admin: "管理员" };

export function MobileAccountSettings() {
  const [profile, setProfile] = useState<MobileUserProfile | null>(null);
  const [username, setUsername] = useState("");
  const [passwords, setPasswords] = useState({ old: "", next: "", confirmation: "" });
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [kaiBinding, setKaiBinding] = useState<KaiBindingStatus | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const bindingExchangeStarted = useRef(false);

  const load = useCallback(async () => {
    try {
      const result = await getMobileUserProfile();
      setProfile(result);
      setUsername(result.username || "");
    } catch (reason) {
      setError(errorMessage(reason));
      return;
    }
    try { setKaiBinding(await getKaiBindingStatus()); }
    catch { setKaiBinding(null); }
  }, []);
  useEffect(() => {
    const url = new URL(window.location.href);
    const bindTicket = url.searchParams.get("kai_bind_ticket");
    const kaiError = url.searchParams.get("kai_error");
    if (kaiError) {
      setError(kaiError === "access_denied" ? "已取消 Kai 身份绑定" : "Kai 身份绑定失败，请重试");
      url.searchParams.delete("kai_error");
      window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    }
    if (!bindTicket || bindingExchangeStarted.current) {
      void load();
      return;
    }
    bindingExchangeStarted.current = true;
    setBusy("kai");
    exchangeKaiBindingTicket(bindTicket)
      .then(() => {
        setMessage("Kai 身份已绑定，之后可直接使用 Kai 登录");
        url.searchParams.delete("kai_bind_ticket");
        window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
        return load();
      })
      .catch((reason) => setError(errorMessage(reason)))
      .finally(() => setBusy(""));
  }, [load]);

  async function run(key: string, action: () => Promise<unknown>, success: string) {
    setBusy(key); setError(""); setMessage("");
    try { await action(); setMessage(success); await load(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(""); }
  }

  function saveProfile(event: FormEvent) {
    event.preventDefault();
    const value = username.trim();
    if (value.length < 2) { setError("用户名至少需要 2 个字符"); return; }
    void run("profile", () => updateMobileUserProfile(value), "账户资料已保存");
  }

  function changePassword(event: FormEvent) {
    event.preventDefault();
    if (passwords.next !== passwords.confirmation) { setError("两次输入的新密码不一致"); return; }
    void run("password", async () => {
      await changeMobilePassword(passwords.old, passwords.next);
      setPasswords({ old: "", next: "", confirmation: "" });
    }, "密码已更新");
  }

  async function chooseAvatar(file?: File) {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { setError("头像图片不能超过 2MB"); return; }
    await run("avatar", () => uploadMobileAvatar(file), "头像已更新");
    if (fileRef.current) fileRef.current.value = "";
  }

  async function bindKaiIdentity() {
    setBusy("kai"); setError(""); setMessage("");
    try {
      const result = await startKaiBinding();
      if (!result.authorization_url) throw new Error("Kai 统一认证未返回授权地址");
      window.location.assign(result.authorization_url);
    } catch (reason) {
      setError(errorMessage(reason));
      setBusy("");
    }
  }

  if (!profile && !error) return <section className="workspace-page"><div className="commerce-loading">正在读取账户资料…</div></section>;
  return <section className="workspace-page mobile-account-settings">
    <div className="workspace-page__head"><p>ACCOUNT / PROFILE</p><h1>账户设置</h1><span>管理用户名、头像、密码和身份角色。</span></div>
    {error && <div className="commerce-error">{error}</div>}{message && <div className="commerce-success">{message}</div>}
    {profile && <div className="mobile-account-grid">
      <aside className="mobile-account-card">
        <div className="mobile-account-avatar">{profile.avatar ? <img src={mobileAvatarUrl(profile.avatar)} alt="账户头像" /> : <UserCircle size={68}/>}<button type="button" disabled={Boolean(busy)} onClick={() => fileRef.current?.click()}><Camera size={15}/>{busy === "avatar" ? "上传中" : "更换头像"}</button><input ref={fileRef} hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => void chooseAvatar(event.target.files?.[0])}/></div>
        <small>统一账户</small><h2>{profile.username}</h2><span>{roleLabel[profile.role || ""] || profile.role}</span>
        <dl><div><dt>手机号</dt><dd>{profile.phone_bound && profile.phone ? profile.phone : "未绑定"}</dd></div><div><dt>商家审核</dt><dd>{profile.supplier_status || "未申请"}</dd></div></dl>
      </aside>
      <main className="mobile-account-forms">
        <form className="mobile-business-form" onSubmit={saveProfile}><header><UserCircle size={21}/><div><small>PROFILE</small><h2>基本资料</h2></div></header><label>用户名<input minLength={2} maxLength={64} value={username} onChange={(event) => setUsername(event.target.value)} required/></label><p>手机号是登录凭证，如需更换请完成身份验证流程。</p><button className="commerce-primary" disabled={Boolean(busy)}>{busy === "profile" ? "保存中…" : "保存资料"}</button></form>
        <form className="mobile-business-form" onSubmit={changePassword}><header><Key size={21}/><div><small>SECURITY</small><h2>修改密码</h2></div></header><label>原密码<input type="password" autoComplete="current-password" value={passwords.old} onChange={(event) => setPasswords({ ...passwords, old: event.target.value })} required/></label><label>新密码<input type="password" minLength={6} maxLength={64} autoComplete="new-password" value={passwords.next} onChange={(event) => setPasswords({ ...passwords, next: event.target.value })} required/></label><label>确认新密码<input type="password" minLength={6} maxLength={64} autoComplete="new-password" value={passwords.confirmation} onChange={(event) => setPasswords({ ...passwords, confirmation: event.target.value })} required/></label><button className="commerce-primary" disabled={Boolean(busy)}>{busy === "password" ? "更新中…" : "更新密码"}</button></form>
        <section className="mobile-role-card"><header><Storefront size={21}/><div><small>ROLE</small><h2>使用身份</h2></div></header><p>{profile.supplier_status === "approved" ? "你的商家审核已通过，可以在个人用户和商家工作台之间切换。" : "通过商家审核后，才可以切换到商家工作台。"}</p><button disabled={Boolean(busy) || profile.supplier_status !== "approved"} onClick={() => void run("role", async () => { await switchMobileRole(); window.location.assign("/account"); }, "身份已切换")}><ShieldCheck size={16}/>{busy === "role" ? "切换中…" : `切换为${profile.role === "supplier" ? "个人用户" : "商家"}`}</button></section>
        <section className="mobile-role-card"><header><ShieldCheck size={21}/><div><small>KAI IDENTITY</small><h2>Kai 身份绑定</h2></div></header><p>{kaiBinding?.bound ? "当前账号已绑定 Kai 统一身份，可在 Web、iOS 和 Android 使用同一身份登录。" : "绑定会明确将当前 KAI 账号与 Kai 统一身份关联，不会创建第二个业务账号。"}</p><button className="commerce-primary" disabled={Boolean(busy) || kaiBinding?.bound === true} onClick={() => void bindKaiIdentity()}><ShieldCheck size={16}/>{busy === "kai" ? "正在处理…" : kaiBinding?.bound ? "已绑定 Kai" : "前往 Kai 绑定"}</button></section>
      </main>
    </div>}
  </section>;
}
