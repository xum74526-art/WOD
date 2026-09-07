"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CheckCircle, EnvelopeSimple, WarningCircle } from "@phosphor-icons/react";
import { confirmEmailVerification } from "@/lib/api";
import { recoveryTokenFromUrl } from "@/lib/account-recovery-url";
import { useI18n } from "@/components/locale-root";

export function EmailVerificationResult() {
  const { locale, t } = useI18n();
  const [state, setState] = useState<"loading" | "success" | "error">("loading");
  const [errorDetail, setErrorDetail] = useState("");
  const verificationStarted = useRef(false);
  useEffect(() => {
    if (verificationStarted.current) return;
    verificationStarted.current = true;
    const recovered = recoveryTokenFromUrl(window.location.href, ["token"]);
    window.history.replaceState(null, "", recovered.cleanPath);
    const token = recovered.token;
    if (!token) { setState("error"); setErrorDetail("missing"); return; }
    confirmEmailVerification(token)
      .then(() => setState("success"))
      .catch((reason) => {
        setState("error");
        setErrorDetail(reason instanceof Error ? reason.message : "");
      });
  }, []);
  const Icon = state === "success" ? CheckCircle : state === "error" ? WarningCircle : EnvelopeSimple;
  const message = state === "success"
    ? t("auth.recovery.verify.success", "绑定邮箱验证完成")
    : state === "loading"
      ? t("auth.recovery.verify.loading", "正在验证绑定邮箱…")
      : errorDetail === "missing"
        ? t("auth.recovery.verify.missingToken", "验证链接缺少令牌")
        : locale === "en" || !errorDetail
          ? t("auth.recovery.verify.invalid", "验证链接无效或已过期")
          : errorDetail;
  return <main className="auth-result-page"><section><Icon size={34}/><p>LINKED EMAIL / VERIFICATION</p><h1>{message}</h1><span>{state === "success" ? t("auth.recovery.verify.successDescription", "该邮箱现在可以用于账号找回和密码重置。") : state === "loading" ? t("auth.recovery.verify.loadingDescription", "请稍候，不要关闭页面。") : t("auth.recovery.verify.errorDescription", "可以登录后在账户设置中重新发送验证邮件。")}</span><Link href={state === "success" ? "/account/settings" : "/login"}>{state === "success" ? t("auth.recovery.verify.accountSettings", "进入账户设置") : t("auth.recovery.verify.backLogin", "返回登录")}</Link></section></main>;
}
