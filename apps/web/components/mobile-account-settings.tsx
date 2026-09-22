"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Camera, EnvelopeSimple, Key, Phone, ShieldCheck, Storefront, UserCircle } from "@phosphor-icons/react";
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
  getAccountRecoveryConfig,
  getKaiBindingStatus,
  getLoginPhoneStatus,
  getRecoveryEmailStatus,
  configureLoginPhone,
  requestRecoveryEmailVerification,
  startKaiBinding,
  type AccountRecoveryConfig,
  type KaiBindingStatus,
  type LoginPhoneStatus,
  type RecoveryEmailStatus,
} from "@/lib/api";
import { useI18n } from "@/components/locale-root";
import { localizePersonName, personNameInputValue, personNameSaveValue } from "@/lib/person-name";
import { ContactPhone } from "@/components/contact-phone";
import { loginHref } from "@/lib/auth-navigation";

const roleLabels: Record<string, { key: string; zh: string }> = {
  personal: { key: "settings.role.personal", zh: "个人用户" },
  supplier: { key: "settings.role.supplier", zh: "商家" },
  admin: { key: "settings.role.admin", zh: "管理员" },
};

export function MobileAccountSettings() {
  const { locale, t } = useI18n();
  const [profile, setProfile] = useState<MobileUserProfile | null>(null);
  const [username, setUsername] = useState("");
  const [usernameEdited, setUsernameEdited] = useState(false);
  const [passwords, setPasswords] = useState({ old: "", next: "", confirmation: "" });
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [kaiBinding, setKaiBinding] = useState<KaiBindingStatus | null>(null);
  const [recoveryConfig, setRecoveryConfig] = useState<AccountRecoveryConfig | null>(null);
  const [recoveryEmail, setRecoveryEmail] = useState<RecoveryEmailStatus | null>(null);
  const [recoveryEmailChecked, setRecoveryEmailChecked] = useState(false);
  const [recoveryForm, setRecoveryForm] = useState({ email: "", currentPassword: "" });
  const [loginPhone, setLoginPhone] = useState<LoginPhoneStatus | null>(null);
  const [loginPhoneForm, setLoginPhoneForm] = useState({ phone: "", password: "", confirmation: "" });
  const fileRef = useRef<HTMLInputElement>(null);
  const bindingExchangeStarted = useRef(false);

  const localizedError = useCallback((reason: unknown) => (
    locale === "en" ? t("settings.error", "账户请求未完成，请稍后重试。") : errorMessage(reason)
  ), [locale, t]);

  const load = useCallback(async () => {
    try {
      const result = await getMobileUserProfile();
      setProfile(result);
      setUsername(result.username || "");
      setUsernameEdited(false);
    } catch (reason) {
      setError(localizedError(reason));
      return;
    }
    try { setKaiBinding(await getKaiBindingStatus()); }
    catch { setKaiBinding(null); }
    try { setLoginPhone(await getLoginPhoneStatus()); }
    catch { setLoginPhone(null); }
    try {
      const status = await getRecoveryEmailStatus();
      setRecoveryEmail(status);
      setRecoveryForm((current) => ({ ...current, email: current.email || status.email || "" }));
    } catch { setRecoveryEmail(null); }
    finally { setRecoveryEmailChecked(true); }
    try { setRecoveryConfig(await getAccountRecoveryConfig()); }
    catch { setRecoveryConfig(null); }
  }, [localizedError]);
  useEffect(() => {
    const url = new URL(window.location.href);
    const bindTicket = url.searchParams.get("kai_bind_ticket");
    const kaiError = url.searchParams.get("kai_error");
    if (kaiError) {
      setError(kaiError === "access_denied" ? t("settings.kaiCanceled", "已取消 Kai 身份绑定") : t("settings.kaiFailed", "Kai 身份绑定失败，请重试"));
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
        setMessage(t("settings.kaiBoundSuccess", "Kai 身份已绑定，之后可直接使用 Kai 登录"));
        url.searchParams.delete("kai_bind_ticket");
        window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
        return load();
      })
      .catch((reason) => setError(localizedError(reason)))
      .finally(() => setBusy(""));
  }, [load, localizedError, t]);

  async function run(key: string, action: () => Promise<unknown>, success: string) {
    setBusy(key); setError(""); setMessage("");
    try { await action(); setMessage(success); await load(); }
    catch (reason) { setError(localizedError(reason)); }
    finally { setBusy(""); }
  }

  function saveProfile(event: FormEvent) {
    event.preventDefault();
    const value = personNameSaveValue(profile?.username, username, usernameEdited);
    if (value.length < 2) { setError(t("settings.usernameMinimum", "用户名至少需要 2 个字符")); return; }
    void run("profile", () => updateMobileUserProfile(value), t("settings.profileSaved", "账户资料已保存"));
  }

  function changePassword(event: FormEvent) {
    event.preventDefault();
    if (passwords.next !== passwords.confirmation) { setError(t("settings.passwordMismatch", "两次输入的新密码不一致")); return; }
    void run("password", async () => {
      await changeMobilePassword(passwords.old, passwords.next);
      setPasswords({ old: "", next: "", confirmation: "" });
    }, t("settings.passwordUpdated", "密码已更新"));
  }

  async function requestRecoveryEmail(event: FormEvent) {
    event.preventDefault();
    setBusy("recovery-email"); setError(""); setMessage("");
    try {
      const result = await requestRecoveryEmailVerification(
        recoveryForm.email.trim(),
        recoveryEmail?.current_password_required === false ? undefined : recoveryForm.currentPassword,
      );
      setRecoveryForm((current) => ({ ...current, currentPassword: "" }));
      setMessage(result.already_verified
        ? t("settings.recoveryEmailAlreadyVerified", "该邮箱已经是当前账号的已绑定邮箱")
        : t("settings.recoveryEmailSent", "绑定邮箱验证邮件已发送，请在邮件中完成确认"));
      await load();
    } catch (reason) {
      setError(localizedError(reason));
    } finally {
      setBusy("");
    }
  }

  async function configurePhoneLogin(event: FormEvent) {
    event.preventDefault();
    if (loginPhoneForm.password !== loginPhoneForm.confirmation) {
      setError(t("settings.passwordMismatch", "两次输入的新密码不一致"));
      return;
    }
    setBusy("login-phone"); setError(""); setMessage("");
    try {
      await configureLoginPhone(loginPhoneForm.phone, loginPhoneForm.password);
      setLoginPhoneForm({ phone: "", password: "", confirmation: "" });
      setMessage(t("settings.loginPhoneConfigured", "登录手机号和密码已设置。"));
      await load();
    } catch (reason) {
      setError(localizedError(reason));
    } finally {
      setBusy("");
    }
  }

  async function chooseAvatar(file?: File) {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { setError(t("settings.avatarLimit", "头像图片不能超过 2MB")); return; }
    await run("avatar", () => uploadMobileAvatar(file), t("settings.avatarUpdated", "头像已更新"));
    if (fileRef.current) fileRef.current.value = "";
  }

  async function bindKaiIdentity() {
    setBusy("kai"); setError(""); setMessage("");
    try {
      const result = await startKaiBinding();
      if (!result.authorization_url) throw new Error(t("settings.kaiNoUrl", "Kai 统一认证未返回授权地址"));
      window.location.assign(result.authorization_url);
    } catch (reason) {
      setError(localizedError(reason));
      setBusy("");
    }
  }

  if (!profile && !error) return <section className="workspace-page"><div className="commerce-loading">{t("settings.loading", "正在读取账户资料…")}</div></section>;
  return <section className="workspace-page mobile-account-settings">
    <div className="workspace-page__head"><p>ACCOUNT / PROFILE</p><h1>{t("settings.title", "账户设置")}</h1><span>{t("settings.description", "管理用户名、头像、密码、绑定邮箱和身份角色。")}</span><ContactPhone /></div>
    {error && <div className="commerce-error">{error}</div>}{message && <div className="commerce-success">{message}</div>}
    {profile && <div className="mobile-account-grid">
      <aside className="mobile-account-card">
        <div className="mobile-account-avatar">{profile.avatar ? <img src={mobileAvatarUrl(profile.avatar)} alt={t("settings.avatarAlt", "账户头像")} /> : <UserCircle size={68}/>}<button type="button" disabled={Boolean(busy)} onClick={() => fileRef.current?.click()}><Camera size={15}/>{busy === "avatar" ? t("settings.uploading", "上传中") : t("settings.changeAvatar", "更换头像")}</button><input ref={fileRef} hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => void chooseAvatar(event.target.files?.[0])}/></div>
        <small>{t("settings.unifiedAccount", "统一账户")}</small><h2>{localizePersonName(profile.username, locale)}</h2><span>{roleLabels[profile.role || ""] ? t(roleLabels[profile.role || ""].key, roleLabels[profile.role || ""].zh) : profile.role}</span>
        <dl><div><dt>{loginPhone?.configured ? t("settings.loginPhone", "登录手机号") : t("settings.phone", "手机号")}</dt><dd>{loginPhone?.configured ? loginPhone.phone_masked || "—" : profile.phone_bound && profile.phone ? profile.phone : t("settings.notBound", "未绑定")}</dd></div><div><dt>{t("settings.supplierReview", "商家审核")}</dt><dd>{profile.supplier_status === "approved" ? t("settings.supplierApproved", "已通过") : profile.supplier_status === "pending" ? t("settings.supplierPending", "审核中") : profile.supplier_status === "rejected" ? t("settings.supplierRejected", "未通过") : t("settings.notApplied", "未申请")}</dd></div></dl>
      </aside>
      <main className="mobile-account-forms">
        <form className="mobile-business-form" onSubmit={saveProfile}><header><UserCircle size={21}/><div><small>PROFILE</small><h2>{t("settings.profile", "基本资料")}</h2></div></header><label>{t("settings.username", "用户名")}<input minLength={2} maxLength={64} value={personNameInputValue(username, locale, usernameEdited)} onChange={(event) => { setUsernameEdited(true); setUsername(event.target.value); }} required/></label><p>{t("settings.phoneCredential", "手机号是登录凭证，如需更换请完成身份验证流程。")}</p><button className="commerce-primary" disabled={Boolean(busy)}>{busy === "profile" ? t("settings.saving", "保存中…") : t("settings.saveProfile", "保存资料")}</button></form>
        {loginPhone?.can_configure && <form className="mobile-business-form" onSubmit={(event) => void configurePhoneLogin(event)}><header><Phone size={21}/><div><small>LOGIN PHONE</small><h2>{t("settings.loginPhone", "设置登录手机号")}</h2></div></header><p>{t("settings.loginPhoneNotice", "登录手机号仅作为登录标识，尚未经过短信核验。")}</p><label>{t("settings.loginPhone", "登录手机号")}<input type="tel" inputMode="numeric" autoComplete="tel" pattern="1[0-9]{10}" minLength={11} maxLength={11} value={loginPhoneForm.phone} onChange={(event) => setLoginPhoneForm({ ...loginPhoneForm, phone: event.target.value.replace(/\D/g, "").slice(0, 11) })} required/></label><label>{t("settings.setPassword", "设置登录密码")}<input type="password" minLength={8} maxLength={64} autoComplete="new-password" value={loginPhoneForm.password} onChange={(event) => setLoginPhoneForm({ ...loginPhoneForm, password: event.target.value })} required/></label><label>{t("settings.confirmPassword", "确认新密码")}<input type="password" minLength={8} maxLength={64} autoComplete="new-password" value={loginPhoneForm.confirmation} onChange={(event) => setLoginPhoneForm({ ...loginPhoneForm, confirmation: event.target.value })} required/></label><button className="commerce-primary" disabled={Boolean(busy)}>{busy === "login-phone" ? t("settings.saving", "保存中…") : t("settings.saveLoginPhone", "保存登录手机号")}</button></form>}
        {loginPhone?.configured && <section className="mobile-role-card"><header><Phone size={21}/><div><small>LOGIN PHONE</small><h2>{t("settings.loginPhone", "登录手机号")}</h2></div></header><p>{t("settings.loginPhoneConfiguredDescription", "当前登录手机号：{phone}。该号码只用于登录标识，未经过短信核验。", { phone: loginPhone.phone_masked || "—" })}</p></section>}
        {(loginPhone?.configured || profile.password_set !== false) && <form className="mobile-business-form" onSubmit={changePassword}><header><Key size={21}/><div><small>SECURITY</small><h2>{t("settings.changePassword", "修改密码")}</h2></div></header><label>{t("settings.currentPassword", "原密码")}<input type="password" autoComplete="current-password" value={passwords.old} onChange={(event) => setPasswords({ ...passwords, old: event.target.value })} required/></label><label>{t("settings.newPassword", "新密码")}<input type="password" minLength={6} maxLength={64} autoComplete="new-password" value={passwords.next} onChange={(event) => setPasswords({ ...passwords, next: event.target.value })} required/></label><label>{t("settings.confirmPassword", "确认新密码")}<input type="password" minLength={6} maxLength={64} autoComplete="new-password" value={passwords.confirmation} onChange={(event) => setPasswords({ ...passwords, confirmation: event.target.value })} required/></label><button className="commerce-primary" disabled={Boolean(busy)}>{busy === "password" ? t("settings.updating", "更新中…") : t("settings.updatePassword", "更新密码")}</button></form>}
        <form className="mobile-business-form mobile-recovery-email-form" onSubmit={(event) => void requestRecoveryEmail(event)}><header><EnvelopeSimple size={21}/><div><small>EMAIL BINDING</small><h2>{t("settings.recoveryEmail", "绑定邮箱")}</h2></div></header><p>{!recoveryEmailChecked ? t("settings.recoveryEmailLoading", "正在读取绑定邮箱状态…") : recoveryEmail?.verified && recoveryEmail.email ? `${t("settings.recoveryEmailVerified", "已绑定邮箱")}: ${recoveryEmail.email}` : recoveryEmail ? t("settings.recoveryEmailNotBound", "尚未绑定邮箱") : t("settings.recoveryEmailUnknown", "暂时无法读取绑定邮箱状态")}</p>{recoveryEmail?.kai_reauth_required ? <p>{t("settings.recoveryEmailKaiReauthRequired", "本次 KAI 身份确认已过期，请重新使用 KAI 登录后绑定邮箱。")} <Link href={loginHref("/account/settings")}>{t("settings.recoveryEmailKaiReauthAction", "前往 KAI 登录")}</Link></p> : <><label>{t("settings.recoveryEmailAddress", "绑定邮箱")}<input type="email" autoComplete="email" maxLength={320} value={recoveryForm.email} onChange={(event) => setRecoveryForm({ ...recoveryForm, email: event.target.value })} required disabled={recoveryConfig?.email_enabled === false}/></label>{recoveryEmail?.current_password_required !== false && <label>{t("settings.currentPassword", "当前密码")}<input type="password" autoComplete="current-password" maxLength={64} value={recoveryForm.currentPassword} onChange={(event) => setRecoveryForm({ ...recoveryForm, currentPassword: event.target.value })} required disabled={recoveryConfig?.email_enabled === false}/></label>}<p>{recoveryEmail?.current_password_required === false ? t("settings.recoveryEmailKaiSessionNotice", "本次 KAI 登录会话已完成身份确认，可直接发送邮箱验证；过期后请重新使用 KAI 登录。") : t("settings.recoveryEmailNotice", "绑定或更换邮箱后，需要通过邮件中的安全链接完成验证。")}</p><button type="submit" className="commerce-primary" disabled={Boolean(busy) || recoveryConfig?.email_enabled === false}>{busy === "recovery-email" ? t("settings.sending", "发送中…") : recoveryConfig?.email_enabled === false ? t("settings.emailRecoveryUnavailable", "邮箱服务暂不可用") : recoveryEmail?.verified ? t("settings.changeRecoveryEmail", "验证并更换绑定邮箱") : t("settings.bindRecoveryEmail", "发送验证邮件")}</button></>}</form>
        <section className="mobile-role-card"><header><Storefront size={21}/><div><small>ROLE</small><h2>{t("settings.activeRole", "使用身份")}</h2></div></header><p>{profile.supplier_status === "approved" ? t("settings.roleApprovedDescription", "你的商家审核已通过，可以在个人用户和商家工作台之间切换。") : t("settings.rolePendingDescription", "通过商家审核后，才可以切换到商家工作台。")}</p><button disabled={Boolean(busy) || profile.supplier_status !== "approved"} onClick={() => void run("role", async () => { await switchMobileRole(); window.location.assign("/account"); }, t("settings.roleSwitched", "身份已切换"))}><ShieldCheck size={16}/>{busy === "role" ? t("settings.switching", "切换中…") : profile.role === "supplier" ? t("settings.switchPersonal", "切换为个人用户") : t("settings.switchSupplier", "切换为商家")}</button></section>
        <section className="mobile-role-card"><header><ShieldCheck size={21}/><div><small>KAI IDENTITY</small><h2>{t("settings.kaiBinding", "Kai 身份绑定")}</h2></div></header><p>{kaiBinding?.bound ? t("settings.kaiBoundDescription", "当前账号已绑定 Kai 统一身份，可在 Web、iOS 和 Android 使用同一身份登录。") : t("settings.kaiBindingDescription", "绑定会明确将当前KAI星算账号与 Kai 统一身份关联，不会创建第二个业务账号。")}</p><button className="commerce-primary" disabled={Boolean(busy) || kaiBinding?.bound === true} onClick={() => void bindKaiIdentity()}><ShieldCheck size={16}/>{busy === "kai" ? t("settings.processing", "正在处理…") : kaiBinding?.bound ? t("settings.kaiBound", "已绑定 Kai") : t("settings.bindKai", "前往 Kai 绑定")}</button></section>
        <section className="mobile-role-card"><h2>{locale === "en" ? "Account deletion" : "账号注销"}</h2><p>{locale === "en" ? "Check outstanding items and verify your identity before permanently deleting your KAI Star account." : "注销前将检查未结事项并验证身份，注销完成后KAI星算账号无法恢复。"}</p><Link className="outline-link" href="/account-deletion">{locale === "en" ? "Request account deletion" : "申请注销账号"}</Link></section>
      </main>
    </div>}
  </section>;
}
