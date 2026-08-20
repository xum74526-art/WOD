"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle, EnvelopeSimple, Eye, EyeSlash, Key, LockKey, ShieldCheck, User } from "@phosphor-icons/react";
import { Button, Callout, Checkbox, TextField } from "@radix-ui/themes";
import { getKaiAuthConfig, kaiWebAuthorizationUrl, passwordLogin, passwordRegister } from "@/lib/api";

type AuthPanelProps = { mode: "login" | "register" };

function safeReturnPath() {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("return_to") || params.get("next");
  if (!requested) return "/";
  return requested.startsWith("/") && !requested.startsWith("//") ? requested : "/";
}

export function AuthPanel({ mode }: AuthPanelProps) {
  const isRegister = mode === "register";
  const [method, setMethod] = useState<"password" | "kai">("password");
  const [name, setName] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"info" | "error">("info");
  const [switchHref, setSwitchHref] = useState(isRegister ? "/login" : "/register");
  const [kaiConfigured, setKaiConfigured] = useState<boolean | null>(null);

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
      };
      setMessageTone("error");
      setMessage(errors[kaiError] || "Kai 登录失败，请重试");
      setMethod("kai");
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
      if (isRegister) await passwordRegister({ display_name: name.trim(), identifier: identifier.trim(), password });
      else await passwordLogin({ identifier: identifier.trim(), password });
      const destination = safeReturnPath();
      setMessageTone("info");
      setMessage(`${isRegister ? "账号已创建" : "登录成功"}，${destination === "/" ? "正在返回首页" : "正在返回之前的页面"}`);
      window.location.assign(destination);
    } catch (error) {
      setMessageTone("error");
      setMessage(error instanceof Error ? error.message : "网络连接失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="auth-panel" aria-labelledby="auth-title">
      <div className="auth-panel__heading">
        <p className="auth-eyebrow">{isRegister ? "CREATE YOUR ACCOUNT" : "WELCOME BACK"}</p>
        <h1 id="auth-title">{isRegister ? "创建账号" : "欢迎回来"}</h1>
        <p>{isRegister ? "创建买家账号，添加 SSH 公钥后即可租用服务器。" : "登录后管理服务器租约、SSH 公钥或商家资源。"}</p>
      </div>

      <div className="auth-methods" role="tablist" aria-label="登录方式">
        <button type="button" role="tab" data-state={method === "password" ? "active" : "inactive"} aria-selected={method === "password"} onClick={() => setMethod("password")}>
          <Key size={16} />邮箱或手机号
        </button>
        <button type="button" role="tab" data-state={method === "kai" ? "active" : "inactive"} aria-selected={method === "kai"} onClick={() => setMethod("kai")}>
          <ShieldCheck size={16} />Kai 统一认证
        </button>
      </div>

      <form className="auth-form auth-form--email" onSubmit={submit}>
        {method === "password" && isRegister && (
          <label className="form-field">
            <span>用户昵称</span>
            <TextField.Root value={name} onChange={(event) => setName(event.target.value)} minLength={2} maxLength={64} autoComplete="name" required>
              <TextField.Slot><User size={17} /></TextField.Slot>
            </TextField.Root>
          </label>
        )}
        {method === "password" ? (
          <>
            <label className="form-field">
              <span>邮箱或手机号</span>
              <TextField.Root type="text" inputMode="email" autoComplete="username" value={identifier} onChange={(event) => setIdentifier(event.target.value)} minLength={3} maxLength={255} required>
                <TextField.Slot><EnvelopeSimple size={17} /></TextField.Slot>
              </TextField.Root>
            </label>
            <div className="form-field">
              <span className="form-field__label"><label htmlFor="auth-password">{isRegister ? "设置密码" : "密码"}</label>{!isRegister && <Link href="/forgot-password">忘记密码？</Link>}</span>
              <TextField.Root id="auth-password" type={passwordVisible ? "text" : "password"} autoComplete={isRegister ? "new-password" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} maxLength={128} required>
                <TextField.Slot><Key size={17} /></TextField.Slot>
                <TextField.Slot side="right"><button className="auth-password-toggle" type="button" aria-label={passwordVisible ? "隐藏输入内容" : "显示输入内容"} aria-pressed={passwordVisible} onClick={() => setPasswordVisible((visible) => !visible)}>{passwordVisible ? <EyeSlash size={17} /> : <Eye size={17} />}</button></TextField.Slot>
              </TextField.Root>
            </div>
          </>
        ) : (
          <div className="kai-auth">
            <div className="kai-auth__mark">KAI</div>
            <h2>{isRegister ? "使用 Kai 创建账号" : "使用 Kai 继续"}</h2>
            <p>KAI 只接收统一身份结果，不会读取或保存你的 Kai 密码。</p>
            <div className="kai-auth__scope"><ShieldCheck size={17}/><span>{kaiConfigured === false ? "管理员尚未配置 Kai 客户端凭据" : "将前往 Kai 完成身份验证，然后安全返回"}</span></div>
          </div>
        )}
        {isRegister && (
          <>
            {method === "password" && <p className="form-note">密码至少 8 个字符，支持最长 128 个字符的密码短语。</p>}
            <label className="auth-consent">
              <Checkbox checked={acceptedTerms} onCheckedChange={(checked) => setAcceptedTerms(checked === true)} />
              <span>我已阅读并同意 <Link href="/terms">用户协议</Link> 和 <Link href="/privacy">隐私说明</Link></span>
            </label>
          </>
        )}
        {message && (
          <Callout.Root className="auth-message" color={messageTone === "error" ? "red" : "cyan"} role="status">
            <Callout.Text>{message}</Callout.Text>
          </Callout.Root>
        )}
        <Button className="auth-submit" type="submit" size="3" disabled={submitting || (method === "kai" && kaiConfigured === false)}>
          {submitting ? "正在处理…" : method === "kai" ? (isRegister ? "使用 Kai 创建账号" : "使用 Kai 继续") : (isRegister ? "创建账号" : "登录")}
        </Button>
        <div className="auth-security-note"><LockKey size={15} /><span>{method === "kai" ? "授权码 + PKCE 保护" : "密码加密验证"} · 登录状态最长保留 14 天</span><CheckCircle size={14} /></div>
      </form>

      <div className="auth-panel__footer">
        <p>{isRegister ? "已经有 KAI 账号？" : "第一次使用 KAI？"}<Link href={switchHref}>{isRegister ? "返回登录" : "创建账号"}</Link></p>
        <div><Link href="/privacy">隐私说明</Link><Link href="/terms">用户协议</Link><Link href="/help">登录帮助</Link></div>
      </div>
    </section>
  );
}
