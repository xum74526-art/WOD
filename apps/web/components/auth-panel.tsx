"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowClockwise, CheckCircle, Eye, EyeSlash, Key, LockKey, Phone, ShieldCheck, User } from "@phosphor-icons/react";
import { Button, Callout, Checkbox, TextField } from "@radix-ui/themes";
import { exchangeKaiTicket, getAuthCaptcha, getKaiAuthConfig, kaiWebAuthorizationUrl, passwordLogin, passwordRegister } from "@/lib/api";
import { safeReturnPath as normalizeReturnPath } from "@/lib/auth-navigation";
import { useI18n } from "@/components/locale-root";
import { ContactPhone } from "@/components/contact-phone";

type AuthPanelProps = { mode: "login" | "register" };
const PENDING_KAI_INTENT_KEY = "wod_kai_auth_intent";
const KAI_REGISTRATION_NOTICE_KEY = "wod_kai_registration_notice";
// The server keeps challenges for 300 seconds; expire locally 30 seconds early.
const CAPTCHA_FRESHNESS_MS = 270_000;

type Translate = (key: string, fallback: string, values?: Record<string, string | number>) => string;

function localizedAuthError(error: unknown, t: Translate) {
  if (!(error instanceof Error) || !error.message.trim()) {
    return t("auth.networkFailed", "网络连接失败，请稍后重试");
  }
  const raw = error.message.trim();
  const known: Record<string, [string, string]> = {
    "请求过于频繁，请稍后再试": ["auth.error.rateLimited", "请求过于频繁，请稍后再试。"],
    "验证码错误或已过期": ["auth.error.captchaInvalid", "验证码错误或已过期"],
    "该手机号已注册": ["auth.error.phoneRegistered", "该手机号已注册"],
    "手机号或密码错误": ["auth.error.credentialsInvalid", "手机号或密码错误"],
    "注册信息过长，请缩短后重试": ["auth.error.registrationTooLong", "注册信息过长，请缩短后重试"],
    "邀请码无效，请检查后重试": ["auth.error.inviteInvalid", "邀请码无效，请检查后重试"],
  };
  const match = known[raw.replace(/[。.]+$/u, "")];
  return match ? t(match[0], match[1]) : raw;
}

function safeReturnPath() {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("return_to") || params.get("next");
  return normalizeReturnPath(requested);
}

export function AuthPanel({ mode }: AuthPanelProps) {
  const { t } = useI18n();
  const isRegister = mode === "register";
  const [method, setMethod] = useState<"password" | "kai">("password");
  const [name, setName] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [captchaCode, setCaptchaCode] = useState("");
  const [captcha, setCaptcha] = useState<{ key: string; image: string } | null>(null);
  const [captchaExpiresAt, setCaptchaExpiresAt] = useState(0);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"info" | "error">("info");
  const [switchHref, setSwitchHref] = useState(isRegister ? "/login" : "/register");
  const [kaiConfigured, setKaiConfigured] = useState<boolean | null>(null);
  const kaiExchangeStarted = useRef(false);
  const captchaRefreshPromise = useRef<Promise<boolean> | null>(null);
  const captchaReplacementNoticeRequested = useRef(false);
  const captchaMounted = useRef(false);
  const captchaContextActive = useRef(isRegister && method === "password");
  const translate = useRef(t);
  captchaContextActive.current = isRegister && method === "password";
  translate.current = t;

  const refreshCaptcha = useCallback((showReplacementNotice = false): Promise<boolean> => {
    captchaReplacementNoticeRequested.current ||= showReplacementNotice;
    if (captchaRefreshPromise.current) return captchaRefreshPromise.current;
    setCaptcha(null);
    setCaptchaCode("");
    setCaptchaExpiresAt(0);
    captchaRefreshPromise.current = getAuthCaptcha()
      .then((nextCaptcha) => {
        if (!captchaMounted.current || !captchaContextActive.current) return false;
        setCaptcha(nextCaptcha);
        setCaptchaExpiresAt(Date.now() + CAPTCHA_FRESHNESS_MS);
        if (captchaReplacementNoticeRequested.current) {
          setMessageTone("info");
          setMessage(translate.current("auth.captcha.refreshed", "验证码已更新，请重新输入。"));
        }
        return true;
      })
      .catch(() => {
        if (captchaMounted.current && captchaContextActive.current) {
          setMessageTone("error");
          setMessage(translate.current("auth.captcha.loadFailed", "验证码读取失败，请稍后重试"));
        }
        return false;
      })
      .finally(() => {
        captchaRefreshPromise.current = null;
        captchaReplacementNoticeRequested.current = false;
      });
    return captchaRefreshPromise.current;
  }, []);

  function hasFreshCaptcha(now = Date.now()) {
    const remaining = captchaExpiresAt - now;
    return Boolean(captcha && remaining > 0 && remaining <= CAPTCHA_FRESHNESS_MS);
  }

  useEffect(() => {
    captchaMounted.current = true;
    return () => { captchaMounted.current = false; };
  }, []);

  useEffect(() => {
    if (!isRegister || method !== "password") return;
    let expiryTimer: ReturnType<typeof setTimeout> | null = null;
    const clearExpiryTimer = () => {
      if (expiryTimer) clearTimeout(expiryTimer);
      expiryTimer = null;
    };
    const synchronizeCaptcha = () => {
      clearExpiryTimer();
      if (document.visibilityState !== "visible") return;
      if (!captcha || !captchaExpiresAt) {
        if (!captchaRefreshPromise.current) void refreshCaptcha();
        return;
      }
      const remaining = captchaExpiresAt - Date.now();
      if (remaining <= 0 || remaining > CAPTCHA_FRESHNESS_MS) {
        void refreshCaptcha(Boolean(captchaCode.trim()));
        return;
      }
      expiryTimer = setTimeout(synchronizeCaptcha, remaining);
    };
    const handleVisibilityChange = () => synchronizeCaptcha();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    synchronizeCaptcha();
    return () => {
      clearExpiryTimer();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [captcha, captchaCode, captchaExpiresAt, isRegister, method, refreshCaptcha]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedReturnTo = params.get("return_to") || params.get("next");
    const returnTo = requestedReturnTo ? normalizeReturnPath(requestedReturnTo) : "";
    const suffix = returnTo ? `?return_to=${encodeURIComponent(returnTo)}` : "";
    setSwitchHref(`${isRegister ? "/login" : "/register"}${suffix}`);
    const kaiError = params.get("kai_error");
    const pendingKaiIntent = window.sessionStorage.getItem(PENDING_KAI_INTENT_KEY);
    if (kaiError) {
      window.sessionStorage.removeItem(PENDING_KAI_INTENT_KEY);
      if (kaiError === "identity_not_bound" && pendingKaiIntent === "register" && !isRegister) {
        window.sessionStorage.setItem(KAI_REGISTRATION_NOTICE_KEY, "complete");
        window.location.replace(`/register${suffix}`);
        return;
      }
      const errors: Record<string, [string, string]> = {
        access_denied: ["auth.kaiError.accessDenied", "已取消 KAI 授权"],
        identity_not_bound: ["auth.kaiError.identityNotBound", "该 KAI 身份尚未绑定，请先使用手机号登录，再到账户设置中绑定"],
        identity_conflict: ["auth.kaiError.identityConflict", "KAI 身份与现有账号冲突，请联系支持"],
        missing_code: ["auth.kaiError.missingCode", "KAI 未返回有效授权信息"],
        invalid_issuer: ["auth.kaiError.invalidIssuer", "KAI 身份签发方无效"],
        authorization_failed: ["auth.kaiError.authorizationFailed", "KAI 身份验证失败，请重新授权"],
      };
      setMessageTone("error");
      const errorCopy = errors[kaiError];
      setMessage(errorCopy ? t(errorCopy[0], errorCopy[1]) : t("auth.kaiError.fallback", "KAI 登录失败，请重试"));
      setMethod("kai");
    }
    if (isRegister && window.sessionStorage.getItem(KAI_REGISTRATION_NOTICE_KEY) === "complete") {
      window.sessionStorage.removeItem(KAI_REGISTRATION_NOTICE_KEY);
      setMessageTone("info");
      setMessage(t("auth.kai.registrationComplete", "KAI 注册已完成。请继续创建手机号账号，登录后再到账户设置中绑定 KAI 身份。"));
      setMethod("password");
    }
    const kaiTicket = params.get("kai_ticket");
    if (kaiTicket && !kaiExchangeStarted.current) {
      window.sessionStorage.removeItem(PENDING_KAI_INTENT_KEY);
      kaiExchangeStarted.current = true;
      setMethod("kai");
      setSubmitting(true);
      setMessageTone("info");
      setMessage(t("auth.kai.sessionCreating", "KAI 身份已确认，正在建立 Web 安全会话…"));
      exchangeKaiTicket(kaiTicket)
        .then((result) => window.location.replace(normalizeReturnPath(result.return_to)))
        .catch((reason) => {
          setMessageTone("error");
          setMessage(reason instanceof Error
            ? localizedAuthError(reason, t)
            : t("auth.kai.ticketInvalid", "KAI 登录票据无效或已过期"));
          setSubmitting(false);
        });
    }
    getKaiAuthConfig()
      .then((config) => setKaiConfigured(config.configured))
      .catch(() => setKaiConfigured(false));
  }, [isRegister]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    if (isRegister && !acceptedTerms) {
      setMessageTone("error");
      setMessage(t("auth.termsRequired", "请先阅读并同意用户协议和隐私说明"));
      return;
    }
    if (isRegister && method === "password" && !hasFreshCaptcha()) {
      await refreshCaptcha(true);
      return;
    }
    setSubmitting(true);
    try {
      if (method === "kai") {
        if (!kaiConfigured) throw new Error(t("auth.kai.notConfigured", "KAI 统一认证尚未配置"));
        window.sessionStorage.setItem(PENDING_KAI_INTENT_KEY, mode);
        window.location.assign(kaiWebAuthorizationUrl(mode, safeReturnPath()));
        return;
      }
      if (isRegister) {
        if (!captcha) throw new Error(t("auth.captcha.refreshFirst", "请刷新图形验证码后重试"));
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
      setMessage(t("auth.successMessage", "{action}，{destination}", {
        action: isRegister ? t("auth.accountCreated", "账号已创建") : t("auth.signedIn", "登录成功"),
        destination: destination === "/"
          ? t("auth.returningHome", "正在返回首页")
          : t("auth.returningPrevious", "正在返回之前的页面"),
      }));
      window.location.assign(destination);
    } catch (error) {
      setMessageTone("error");
      setMessage(localizedAuthError(error, t));
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
        <p className="auth-eyebrow">{isRegister ? t("auth.register.kicker", "创建你的账号") : t("auth.login.kicker", "欢迎回来")}</p>
        <h1 id="auth-title">{isRegister ? t("auth.register.title", "创建账号") : t("auth.login.title", "欢迎回来")}</h1>
        <p>{isRegister ? t("auth.register.desc", "创建统一账户，集中管理订单、资产和钱包数据。") : t("auth.login.desc", "登录统一账户，查看订单、资产和钱包数据。")}</p>
      </div>

      <div className="auth-methods" role="tablist" aria-label={isRegister ? t("auth.method.register", "注册方式") : t("auth.method.login", "登录方式")}>
        <button type="button" role="tab" data-state={method === "password" ? "active" : "inactive"} aria-selected={method === "password"} onClick={() => setMethod("password")}>
          <Key size={16}/>{t("auth.phone", "手机号")}
        </button>
        <button type="button" role="tab" data-state={method === "kai" ? "active" : "inactive"} aria-selected={method === "kai"} onClick={() => setMethod("kai")}>
          <ShieldCheck size={16}/>{t("auth.kai", "KAI 统一认证")}
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
                <TextField.Slot side="right"><button className="auth-password-toggle" type="button" aria-label={passwordVisible ? t("auth.password.hide", "隐藏输入内容") : t("auth.password.show", "显示输入内容")} aria-pressed={passwordVisible} onClick={() => setPasswordVisible((visible) => !visible)}>{passwordVisible ? <EyeSlash size={17}/> : <Eye size={17}/>}</button></TextField.Slot>
              </TextField.Root>
            </div>
            {isRegister && <>
              <label className="form-field">
                <span>{t("auth.invite", "邀请码（选填）")}</span>
                <TextField.Root type="text" autoComplete="off" value={inviteCode} onChange={(event) => setInviteCode(event.target.value.toUpperCase())} maxLength={16} />
              </label>
              <label className="form-field">
                <span>{t("auth.captcha", "图形验证码")}</span>
                <div className="auth-captcha-row">
                  <TextField.Root type="text" autoComplete="off" value={captchaCode} onChange={(event) => setCaptchaCode(event.target.value.toUpperCase().slice(0, 4))} minLength={4} maxLength={4} required />
                  <button type="button" className="auth-captcha-image" onClick={() => { void refreshCaptcha(Boolean(captchaCode.trim())); }} aria-label={t("auth.refreshCaptcha", "刷新图形验证码")}>
                    {captcha ? <img src={captcha.image} alt={t("auth.captcha.imageAlt", "图形验证码")} /> : <ArrowClockwise size={19} />}
                  </button>
                </div>
              </label>
            </>}
          </>
        ) : (
          <div className="kai-auth">
            <div className="kai-auth__mark">KAI</div>
            <h2>{isRegister ? t("auth.kai.createTitle", "创建 KAI 身份") : t("auth.kai.signInTitle", "使用已绑定的 KAI 身份登录")}</h2>
            <p>{t("auth.kai.privacyDescription", "算力星图只接收统一身份结果，不会读取或保存你的 KAI 密码。")}</p>
            <div className="kai-auth__scope"><ShieldCheck size={17}/><span>{kaiConfigured === false
              ? t("auth.kai.credentialsMissing", "管理员尚未配置 KAI 客户端凭据")
              : isRegister
                ? t("auth.kai.registrationScope", "完成 KAI 注册后，请先在此创建手机号账号，再到账户设置中绑定")
                : t("auth.kai.unlinkedScope", "未绑定身份需先用手机号登录，再在账户设置中绑定")}</span></div>
          </div>
        )}
        {isRegister && (
          <>
            {method === "password" && <p className="form-note">{t("auth.phoneRule", "手机号需为 11 位；密码至少 6 个字符。")}</p>}
            <label className="auth-consent">
              <Checkbox checked={acceptedTerms} onCheckedChange={(checked) => setAcceptedTerms(checked === true)} />
              <span>{t("auth.termsPrefix", "我已阅读并同意")} <Link href="/terms">{t("footer.terms", "用户协议")}</Link> {t("auth.conjunction.and", "和")} <Link href="/privacy">{t("footer.privacy", "隐私说明")}</Link></span>
            </label>
          </>
        )}
        {message && (
          <Callout.Root className="auth-message" color={messageTone === "error" ? "red" : "cyan"} role="status">
            <Callout.Text>{message}</Callout.Text>
          </Callout.Root>
        )}
        <Button className="auth-submit" type="submit" size="3" disabled={submitting || (method === "kai" && kaiConfigured === false)}>
          {submitting ? t("auth.processing", "正在处理…") : method === "kai" ? (isRegister ? t("auth.kai.continueRegistration", "前往 KAI 注册") : t("auth.kai.signIn", "使用 KAI 登录")) : (isRegister ? t("auth.register", "创建账号") : t("auth.login", "登录"))}
        </Button>
        <div className="auth-security-note"><LockKey size={15}/><span>{method === "kai" ? t("auth.security.kai", "授权码 + PKCE 保护") : t("auth.security.password", "密码加密验证")} · {t("auth.security.session", "登录状态最长保留 2 小时")}</span><CheckCircle size={14}/></div>
      </form>

      <div className="auth-panel__footer">
        <p>{isRegister ? t("auth.already", "已经有算力星图账号？") : t("auth.new", "第一次使用算力星图？")}<Link href={switchHref}>{isRegister ? t("auth.backLogin", "返回登录") : t("auth.create", "创建账号")}</Link></p>
        <div><Link href="/privacy">{t("footer.privacy", "隐私说明")}</Link><Link href="/terms">{t("footer.terms", "用户协议")}</Link><Link href="/help">{t("auth.help", "登录帮助")}</Link></div>
        <ContactPhone />
      </div>
    </section>
  );
}
