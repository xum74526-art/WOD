"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { EnvelopeSimple, Key, ShieldCheck } from "@phosphor-icons/react";
import { Button, Callout, TextField } from "@radix-ui/themes";
import {
  confirmPasswordReset,
  getAccountRecoveryConfig,
  kaiWebAuthorizationUrl,
  requestPasswordReset,
  type AccountRecoveryConfig,
} from "@/lib/api";
import { recoveryTokenFromUrl } from "@/lib/account-recovery-url";
import { useI18n } from "@/components/locale-root";

type RecoveryMethod = "email" | "kai";

const kaiErrors: Record<string, { key: string; zh: string }> = {
  access_denied: { key: "auth.recovery.kaiError.accessDenied", zh: "已取消 KAI 身份验证" },
  identity_not_bound: { key: "auth.recovery.kaiError.identityNotBound", zh: "该 KAI 身份尚未绑定当前算力星图账号，无法用于找回" },
  missing_code: { key: "auth.recovery.kaiError.missingCode", zh: "KAI 未返回有效授权信息" },
  invalid_issuer: { key: "auth.recovery.kaiError.invalidIssuer", zh: "KAI 身份签发方无效" },
  authorization_failed: { key: "auth.recovery.kaiError.authorizationFailed", zh: "KAI 身份验证失败，请重新授权" },
};

export function PasswordRecoveryPanel({ mode }: { mode: "forgot" | "reset" }) {
  const { locale, t } = useI18n();
  const isReset = mode === "reset";
  const [method, setMethod] = useState<RecoveryMethod>("email");
  const [config, setConfig] = useState<AccountRecoveryConfig | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [token, setToken] = useState<string | null>(isReset ? null : "");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);
  const tokenReadStarted = useRef(false);

  useEffect(() => {
    if (isReset && !tokenReadStarted.current) {
      tokenReadStarted.current = true;
      const current = new URL(window.location.href);
      const kaiError = current.searchParams.get("kai_error");
      const recovered = recoveryTokenFromUrl(current.href);
      const clean = new URL(recovered.cleanPath, current.origin);
      clean.searchParams.delete("kai_error");
      window.history.replaceState(null, "", `${clean.pathname}${clean.search}${clean.hash}`);
      setToken(recovered.token);
      if (kaiError) {
        const copy = kaiErrors[kaiError];
        setMessage(copy
          ? t(copy.key, copy.zh)
          : t("auth.recovery.kaiError.fallback", "KAI 身份验证失败，请重试"));
      } else if (!recovered.token) {
        setMessage(t("auth.recovery.missingToken", "重置链接缺少安全令牌，请重新申请"));
      }
    }

    getAccountRecoveryConfig()
      .then((value) => {
        setConfig(value);
        if (!value.email_enabled && value.kai_enabled && !isReset) setMethod("kai");
      })
      .catch(() => setConfig({ email_enabled: false, kai_enabled: false, reset_ttl_seconds: 1800 }));
  }, [isReset, t]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    setSuccess(false);
    if (isReset && password !== confirmation) {
      setMessage(t("auth.recovery.passwordMismatch", "两次输入的密码不一致"));
      return;
    }
    if (isReset && !token) {
      setMessage(t("auth.recovery.missingToken", "重置链接缺少安全令牌，请重新申请"));
      return;
    }
    setSubmitting(true);
    try {
      if (isReset) {
        await confirmPasswordReset(token!, password);
        setToken("");
        setMessage(t("auth.recovery.passwordUpdated", "密码已更新，所有旧登录会话均已退出"));
      } else {
        await requestPasswordReset(email.trim());
        setMessage(t("auth.recovery.emailSent", "如果该邮箱已绑定，密码重置邮件会在几分钟内送达"));
      }
      setSuccess(true);
    } catch (reason) {
      setMessage(locale === "en"
        ? t("auth.recovery.failed", "操作失败，请稍后重试")
        : reason instanceof Error ? reason.message : t("auth.recovery.failed", "操作失败，请稍后重试"));
    } finally {
      setSubmitting(false);
    }
  }

  function startKaiRecovery() {
    setMessage("");
    if (config?.kai_enabled === false) {
      setMessage(t("auth.recovery.kaiUnavailableUseEmail", "KAI 身份找回暂不可用，请通过已绑定邮箱找回账号"));
      return;
    }
    window.location.assign(kaiWebAuthorizationUrl("recover"));
  }

  const emailUnavailable = config?.email_enabled === false;
  const kaiUnavailable = config?.kai_enabled === false;

  return (
    <section className="auth-panel" aria-labelledby="recovery-title">
      <div className="auth-panel__heading">
        <p className="auth-eyebrow">ACCOUNT RECOVERY / SECURE PROOF</p>
        <h1 id="recovery-title">{isReset ? t("auth.recovery.resetTitle", "设置新密码") : t("auth.recovery.title", "找回算力星图账号")}</h1>
        <p>{isReset
          ? t("auth.recovery.resetDescription", "新密码生效后，其他设备上的旧会话会立即退出。")
          : t("auth.recovery.description", "通过已绑定邮箱或已绑定的 KAI 身份找回账号，不提供短信找回。")}</p>
      </div>

      {!isReset && !success && (
        <div className="auth-methods auth-methods--recovery" role="tablist" aria-label={t("auth.recovery.methodsLabel", "账号找回方式")}>
          <button type="button" role="tab" data-state={method === "email" ? "active" : "inactive"} aria-selected={method === "email"} onClick={() => { setMethod("email"); setMessage(""); }}>
            <EnvelopeSimple size={16}/>{t("auth.recovery.emailMethod", "邮箱找回")}
          </button>
          <button type="button" role="tab" data-state={method === "kai" ? "active" : "inactive"} aria-selected={method === "kai"} onClick={() => { setMethod("kai"); setMessage(""); }}>
            <ShieldCheck size={16}/>{t("auth.recovery.kaiMethod", "KAI 身份")}
          </button>
        </div>
      )}

      {!success && (isReset || method === "email") && (
        <form className="auth-form auth-form--email" onSubmit={(event) => void submit(event)}>
          {isReset ? (
            <>
              <label className="form-field">
                <span>{t("auth.recovery.newPassword", "新密码")}</span>
                <TextField.Root type="password" autoComplete="new-password" minLength={8} maxLength={64} required value={password} onChange={(event) => setPassword(event.target.value)}>
                  <TextField.Slot><Key size={17}/></TextField.Slot>
                </TextField.Root>
              </label>
              <label className="form-field">
                <span>{t("auth.recovery.confirmNewPassword", "再次输入新密码")}</span>
                <TextField.Root type="password" autoComplete="new-password" minLength={8} maxLength={64} required value={confirmation} onChange={(event) => setConfirmation(event.target.value)}>
                  <TextField.Slot><Key size={17}/></TextField.Slot>
                </TextField.Root>
              </label>
              <p className="form-note">{t("auth.recovery.secureLinkNote", "安全链接只能使用一次，并会在短时间内失效。")}</p>
            </>
          ) : (
            <>
              <label className="form-field">
                <span>{t("auth.recovery.boundEmail", "已绑定邮箱")}</span>
                <TextField.Root type="email" autoComplete="email" maxLength={320} required disabled={emailUnavailable} value={email} onChange={(event) => setEmail(event.target.value)}>
                  <TextField.Slot><EnvelopeSimple size={17}/></TextField.Slot>
                </TextField.Root>
              </label>
              <p className="form-note">{t("auth.recovery.privacyNote", "为保护账号，无论邮箱是否存在，页面都会显示相同结果。")}</p>
            </>
          )}
          <Button className="auth-submit" type="submit" size="3" disabled={submitting || (isReset && !token) || (!isReset && emailUnavailable)}>
            {submitting
              ? t("auth.recovery.processing", "正在处理…")
              : isReset
                ? t("auth.recovery.submitReset", "更新密码并退出旧会话")
                : emailUnavailable
                  ? t("auth.recovery.emailUnavailable", "邮箱找回暂不可用")
                  : t("auth.recovery.sendReset", "发送密码重置邮件")}
          </Button>
        </form>
      )}

      {!isReset && !success && method === "kai" && (
        <div className="auth-form auth-form--email">
          <div className="kai-auth">
            <div className="kai-auth__mark">KAI</div>
            <h2>{t("auth.recovery.kaiTitle", "使用已绑定的 KAI 身份找回")}</h2>
            <p>{t("auth.recovery.kaiDescription", "前往 KAI 完成一次新的身份验证。算力星图不会读取或保存你的 KAI 密码。")}</p>
            <div className="kai-auth__scope"><ShieldCheck size={17}/><span>{t("auth.recovery.kaiScope", "只有已经与当前算力星图账号绑定的 KAI 身份才能重置密码。")}</span></div>
          </div>
          <Button className="auth-submit" type="button" size="3" disabled={kaiUnavailable} onClick={startKaiRecovery}>
            {kaiUnavailable
              ? t("auth.recovery.kaiUnavailable", "KAI 身份找回暂不可用")
              : t("auth.recovery.kaiContinue", "前往 KAI 验证身份")}
          </Button>
        </div>
      )}

      {message && <Callout.Root className="auth-message" color={success ? "cyan" : "red"} role="status"><Callout.Text>{message}</Callout.Text></Callout.Root>}
      <div className="auth-panel__footer">
        <Link href="/login">{t("auth.recovery.backLogin", "返回手机号登录")}</Link>
        <div><Link href="/privacy">{t("auth.recovery.privacy", "隐私说明")}</Link><Link href="/help">{t("auth.recovery.securityHelp", "安全帮助")}</Link></div>
      </div>
    </section>
  );
}
