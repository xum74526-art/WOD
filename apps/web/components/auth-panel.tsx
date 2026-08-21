"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowClockwise, CheckCircle, Eye, EyeSlash, Key, LockKey, Phone, ShieldCheck, User } from "@phosphor-icons/react";
import { Button, Callout, Checkbox, TextField } from "@radix-ui/themes";
import { exchangeKaiTicket, getAuthCaptcha, getKaiAuthConfig, kaiWebAuthorizationUrl, passwordLogin, passwordRegister } from "@/lib/api";
import { useI18n } from "@/components/locale-root";

type AuthPanelProps = { mode: "login" | "register" };

function safeReturnPath() {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("return_to") || params.get("next");
  if (!requested) return "/";
  return requested.startsWith("/") && !requested.startsWith("//") ? requested : "/";
}

export function AuthPanel({ mode }: AuthPanelProps) {
  const { locale, t } = useI18n();
  const isRegister = mode === "register";
  const [method, setMethod] = useState<"password" | "kai">("password");
  const [name, setName] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [captchaCode, setCaptchaCode] = useState("");
  const [captcha, setCaptcha] = useState<{ key: string; image: string } | null>(null);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"info" | "error">("info");
  const [switchHref, setSwitchHref] = useState(isRegister ? "/login" : "/register");
  const [kaiConfigured, setKaiConfigured] = useState<boolean | null>(null);
  const kaiExchangeStarted = useRef(false);

  function refreshCaptcha() {
    setCaptcha(null);
    getAuthCaptcha()
      .then(setCaptcha)
      .catch(() => {
        setMessageTone("error");
        setMessage("验证码读取失败，请确认手机端后端已启动");
      });
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const returnTo = params.get("return_to") || params.get("next");
    const suffix = returnTo ? `?return_to=${encodeURIComponent(returnTo)}` : "";
    setSwitchHref(`${isRegister ? "/login" : "/register"}${suffix}`);
    const kaiError = params.get("kai_error");
    if (kaiError) {
      const errors: Record<string, string> = {
        access_denied: "已取消 Kai 授权",
        account_not_found: "该 Kai 身份尚未注册，请先创建账号",
        identity_conflict: "Kai 身份与现有账号冲突，请联系支持",
        missing_code: "Kai 未返回有效授权信息",
        invalid_issuer: "Kai 身份签发方无效",
        authorization_failed: "Kai 身份验证失败，请重新授权",
      };
      setMessageTone("error");
      setMessage(errors[kaiError] || "Kai 登录失败，请重试");
      setMethod("kai");
    }
    const kaiTicket = params.get("kai_ticket");
    if (kaiTicket && !kaiExchangeStarted.current) {
      kaiExchangeStarted.current = true;
      setMethod("kai");
      setSubmitting(true);
      setMessageTone("info");
      setMessage("Kai 身份已确认，正在建立 Web 安全会话…");
      exchangeKaiTicket(kaiTicket)
        .then((result) => window.location.replace(result.return_to || "/"))
        .catch((reason) => {
          setMessageTone("error");
          setMessage(reason instanceof Error ? reason.message : "Kai 登录票据无效或已过期");
          setSubmitting(false);
        });
    }
    getKaiAuthConfig()
      .then((config) => setKaiConfigured(config.configured))
      .catch(() => setKaiConfigured(false));
    if (isRegister) refreshCaptcha();
  }, [isRegister]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    if (isRegister && !acceptedTerms) {
      setMessageTone("error");
      setMessage("请先阅读并同意用户协议和隐私说明");
      return;
    }
    setSubmitting(true);
    try {
      if (method === "kai") {
        if (!kaiConfigured) throw new Error("Kai 统一认证尚未配置");
        window.location.assign(kaiWebAuthorizationUrl(mode, safeReturnPath()));
        return;
      }
      if (isRegister) {
        if (!captcha) throw new Error("请刷新图形验证码后重试");
        await passwordRegister({
          display_name: name.trim(),
          identifier: identifier.trim(),
          password,
          captcha_key: captcha.key,
          captcha_code: captchaCode.trim(),
          invite_code: inviteCode.trim() || undefined,
        });
      }
      else await passwordLogin({ identifier: identifier.trim(), password });
      const destination = safeReturnPath();
      setMessageTone("info");
      setMessage(`${isRegister ? "账号已创建" : "登录成功"}，${destination === "/" ? "正在返回首页" : "正在返回之前的页面"}`);
      window.location.assign(destination);
    } catch (error) {
      setMessageTone("error");
      setMessage(error instanceof Error ? error.message : "网络连接失败，请稍后重试");
      if (isRegister && method === "password") {
        setCaptchaCode("");
        refreshCaptcha();
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="auth-panel" aria-labelledby="auth-title">
      <div className="auth-panel__heading">
        <p className="auth-eyebrow">{isRegister ? "CREATE YOUR ACCOUNT" : "WELCOME BACK"}</p>
        <h1 id="auth-title">{isRegister ? t("auth.register.title", "创建账号") : t("auth.login.title", "欢迎回来")}</h1>
        <p>{isRegister ? t("auth.register.desc", "创建与手机端共用的账号，Web 和 App 使用同一份数据。") : t("auth.login.desc", "使用手机端账号登录，查看同一份订单、资产和钱包数据。")}</p>
      </div>

      <div className="auth-methods" role="tablist" aria-label={locale === "en" ? "Sign-in method" : "登录方式"}>
        <button type="button" role="tab" data-state={method === "password" ? "active" : "inactive"} aria-selected={method === "password"} onClick={() => setMethod("password")}>
          <Key size={16}/>{t("auth.phone", "手机号")}
        </button>
        <button type="button" role="tab" data-state={method === "kai" ? "active" : "inactive"} aria-selected={method === "kai"} onClick={() => setMethod("kai")}>
          <ShieldCheck size={16}/>{t("auth.kai", "Kai 统一认证")}
        </button>
      </div>

      <form className="auth-form auth-form--email" onSubmit={submit}>
        {method === "password" && isRegister && (
          <label className="form-field">
            <span>{t("auth.nickname", "用户昵称")}</span>
            <TextField.Root value={name} onChange={(event) => setName(event.target.value)} minLength={2} maxLength={64} autoComplete="name" required>
              <TextField.Slot><User size={17} /></TextField.Slot>
            </TextField.Root>
          </label>
        )}
        {method === "password" ? (
          <>
            <label className="form-field">
              <span>{t("auth.phone", "手机号")}</span>
              <TextField.Root type="tel" inputMode="numeric" autoComplete="tel" value={identifier} onChange={(event) => setIdentifier(event.target.value.replace(/\D/g, "").slice(0, 11))} pattern="1[0-9]{10}" minLength={11} maxLength={11} required>
                <TextField.Slot><Phone size={17} /></TextField.Slot>
              </TextField.Root>
            </label>
            <div className="form-field">
              <span className="form-field__label"><label htmlFor="auth-password">{isRegister ? t("auth.setPassword", "设置密码") : t("auth.password", "密码")}</label>{!isRegister && <Link href="/forgot-password">{t("auth.forgot", "忘记密码？")}</Link>}</span>
              <TextField.Root id="auth-password" type={passwordVisible ? "text" : "password"} autoComplete={isRegister ? "new-password" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} minLength={isRegister ? 6 : 1} maxLength={64} required>
                <TextField.Slot><Key size={17} /></TextField.Slot>
                <TextField.Slot side="right"><button className="auth-password-toggle" type="button" aria-label={passwordVisible ? (locale === "en" ? "Hide password" : "隐藏输入内容") : (locale === "en" ? "Show password" : "显示输入内容")} aria-pressed={passwordVisible} onClick={() => setPasswordVisible((visible) => !visible)}>{passwordVisible ? <EyeSlash size={17}/> : <Eye size={17}/>}</button></TextField.Slot>
              </TextField.Root>
            </div>
            {isRegister && <>
              <label className="form-field">
                <span>{t("auth.invite", "邀请码（选填）")}</span>
                <TextField.Root type="text" autoComplete="off" value={inviteCode} onChange={(event) => setInviteCode(event.target.value.toUpperCase())} maxLength={32} />
              </label>
              <label className="form-field">
                <span>{t("auth.captcha", "图形验证码")}</span>
                <div className="auth-captcha-row">
                  <TextField.Root type="text" autoComplete="off" value={captchaCode} onChange={(event) => setCaptchaCode(event.target.value.toUpperCase().slice(0, 4))} minLength={4} maxLength={4} required />
                  <button type="button" className="auth-captcha-image" onClick={refreshCaptcha} aria-label={t("auth.refreshCaptcha", "刷新图形验证码")}>
                    {captcha ? <img src={captcha.image} alt="图形验证码" /> : <ArrowClockwise size={19} />}
                  </button>
                </div>
              </label>
            </>}
          </>
        ) : (
          <div className="kai-auth">
            <div className="kai-auth__mark">KAI</div>
            <h2>{isRegister ? (locale === "en" ? "Create account with Kai" : "使用 Kai 创建账号") : (locale === "en" ? "Continue with Kai" : "使用 Kai 继续")}</h2>
            <p>{locale === "en" ? "KAI receives only the verified identity result and never reads or stores your Kai password." : "KAI 只接收统一身份结果，不会读取或保存你的 Kai 密码。"}</p>
            <div className="kai-auth__scope"><ShieldCheck size={17}/><span>{kaiConfigured === false ? (locale === "en" ? "Kai client credentials are not configured" : "管理员尚未配置 Kai 客户端凭据") : (locale === "en" ? "You will verify with Kai and return securely" : "将前往 Kai 完成身份验证，然后安全返回")}</span></div>
          </div>
        )}
        {isRegister && (
          <>
            {method === "password" && <p className="form-note">{locale === "en" ? "Use an 11-digit mainland China phone number and a password of at least 6 characters." : "手机号需为 11 位；密码至少 6 个字符。"}</p>}
            <label className="auth-consent">
              <Checkbox checked={acceptedTerms} onCheckedChange={(checked) => setAcceptedTerms(checked === true)} />
              <span>{t("auth.termsPrefix", "我已阅读并同意")} <Link href="/terms">{t("footer.terms", "用户协议")}</Link> {locale === "en" ? "and" : "和"} <Link href="/privacy">{t("footer.privacy", "隐私说明")}</Link></span>
            </label>
          </>
        )}
        {message && (
          <Callout.Root className="auth-message" color={messageTone === "error" ? "red" : "cyan"} role="status">
            <Callout.Text>{message}</Callout.Text>
          </Callout.Root>
        )}
        <Button className="auth-submit" type="submit" size="3" disabled={submitting || (method === "kai" && kaiConfigured === false)}>
          {submitting ? t("auth.processing", "正在处理…") : method === "kai" ? (isRegister ? (locale === "en" ? "Create account with Kai" : "使用 Kai 创建账号") : (locale === "en" ? "Continue with Kai" : "使用 Kai 继续")) : (isRegister ? t("auth.register", "创建账号") : t("auth.login", "登录"))}
        </Button>
        <div className="auth-security-note"><LockKey size={15}/><span>{locale === "en" ? `${method === "kai" ? "Authorization code + PKCE" : "Encrypted password verification"} · Session lasts up to 2 hours` : `${method === "kai" ? "授权码 + PKCE 保护" : "密码加密验证"} · 登录状态最长保留 2 小时`}</span><CheckCircle size={14}/></div>
      </form>

      <div className="auth-panel__footer">
        <p>{isRegister ? t("auth.already", "已经有 KAI 账号？") : t("auth.new", "第一次使用 KAI？")}<Link href={switchHref}>{isRegister ? t("auth.backLogin", "返回登录") : t("auth.create", "创建账号")}</Link></p>
        <div><Link href="/privacy">{t("footer.privacy", "隐私说明")}</Link><Link href="/terms">{t("footer.terms", "用户协议")}</Link><Link href="/help">{t("auth.help", "登录帮助")}</Link></div>
      </div>
    </section>
  );
}
