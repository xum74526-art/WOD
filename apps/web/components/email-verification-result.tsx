"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle, EnvelopeSimple, WarningCircle } from "@phosphor-icons/react";
import { confirmEmailVerification } from "@/lib/api";

export function EmailVerificationResult({ token }: { token: string }) {
  const [state, setState] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("正在验证邮箱…");
  useEffect(() => {
    if (!token) { setState("error"); setMessage("验证链接缺少令牌"); return; }
    confirmEmailVerification(token).then(() => { setState("success"); setMessage("邮箱验证完成"); }).catch((reason) => { setState("error"); setMessage(reason instanceof Error ? reason.message : "验证链接无效或已过期"); });
  }, [token]);
  const Icon = state === "success" ? CheckCircle : state === "error" ? WarningCircle : EnvelopeSimple;
  return <main className="auth-result-page"><section><Icon size={34}/><p>EMAIL / VERIFICATION</p><h1>{message}</h1><span>{state === "success" ? "你现在可以继续商家认证、购买和接收业务邮件。" : state === "loading" ? "请稍候，不要关闭页面。" : "可以登录后在账户与安全中重新发送验证邮件。"}</span><Link href={state === "success" ? "/account/settings" : "/login"}>{state === "success" ? "进入账户与安全" : "返回登录"}</Link></section></main>;
}
