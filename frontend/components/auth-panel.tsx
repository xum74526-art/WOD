"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle, EnvelopeSimple, Eye, EyeSlash, Key, LockKey, User } from "@phosphor-icons/react";
import { Button, Callout, Checkbox, TextField } from "@radix-ui/themes";
import { emailLogin, emailRegister } from "@/lib/api";

type AuthPanelProps = { mode: "login" | "register" };

function safeReturnPath() {
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("return_to") || params.get("next");
  if (!requested) return "/";
  return requested.startsWith("/") && !requested.startsWith("//") ? requested : "/";
}

export function AuthPanel({ mode }: AuthPanelProps) {
  const isRegister = mode === "register";
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"info" | "error">("info");
  const [switchHref, setSwitchHref] = useState(isRegister ? "/login" : "/register");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const returnTo = params.get("return_to") || params.get("next");
    const suffix = returnTo ? `?return_to=${encodeURIComponent(returnTo)}` : "";
    setSwitchHref(`${isRegister ? "/login" : "/register"}${suffix}`);
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
      if (isRegister) await emailRegister({ name: name.trim(), email: email.trim(), password });
      else await emailLogin({ email: email.trim(), password });
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

      <form className="auth-form auth-form--email" onSubmit={submit}>
        {isRegister && (
          <label className="form-field">
            <span>用户昵称</span>
            <TextField.Root value={name} onChange={(event) => setName(event.target.value)} minLength={2} maxLength={64} autoComplete="name" required>
              <TextField.Slot><User size={17} /></TextField.Slot>
            </TextField.Root>
          </label>
        )}
        <label className="form-field">
          <span>邮箱</span>
          <TextField.Root type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} maxLength={255} required>
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
        {isRegister && (
          <>
            <p className="form-note">密码至少 8 个字符，支持最长 128 个字符的密码短语。</p>
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
        <Button className="auth-submit" type="submit" size="3" disabled={submitting}>
          {submitting ? (isRegister ? "正在创建账号…" : "正在登录…") : (isRegister ? "创建账号" : "登录")}
        </Button>
        <div className="auth-security-note"><LockKey size={15} /><span>会话加密保护 · 登录状态最长保留 14 天</span><CheckCircle size={14} /></div>
      </form>

      <div className="auth-panel__footer">
        <p>{isRegister ? "已经有 KAI 账号？" : "第一次使用 KAI？"}<Link href={switchHref}>{isRegister ? "返回登录" : "创建账号"}</Link></p>
        <div><Link href="/privacy">隐私说明</Link><Link href="/terms">用户协议</Link><Link href="/help">登录帮助</Link></div>
      </div>
    </section>
  );
}
