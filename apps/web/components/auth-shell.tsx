"use client";

import Link from "next/link";
import { HardDrives, Key, ShieldCheck } from "@phosphor-icons/react";
import { AuthPanel } from "@/components/auth-panel";
import { PasswordRecoveryPanel } from "@/components/password-recovery-panel";
import { SiteHeader } from "@/components/site-header";
import { useI18n } from "@/components/locale-root";

type AuthShellProps = {
  mode: "login" | "register" | "forgot" | "reset";
};

export function AuthShell({ mode }: AuthShellProps) {
  const { locale, t } = useI18n();
  const copy = mode === "login"
    ? { kicker: "KAI ACCOUNT ACCESS", title: t("auth.intro.login", "连接你的算力资源"), description: locale === "en" ? "One account for buyer, supplier, and platform workspaces, with features shown by role." : "一个账号进入买家、商家与平台工作台，按角色显示对应功能。" }
    : mode === "register"
      ? { kicker: "JOIN KAI", title: t("auth.intro.register", "创建你的 KAI 账号"), description: locale === "en" ? "Add an SSH public key after registration to rent compute and manage connections." : "注册后添加 SSH 公钥，即可租用算力并管理连接。" }
      : { kicker: "ACCOUNT SECURITY", title: t("auth.intro.forgot", "找回 KAI 账号"), description: locale === "en" ? "Update your sign-in credentials and continue managing compute resources and leases." : "通过注册邮箱更新登录凭证，继续管理算力资源和租约。" };

  return (
    <div className="site-page auth-page">
      <SiteHeader authMode="guest" />
      <main className="auth-page__main">
        <section className="auth-page__intro" aria-label={locale === "en" ? "KAI account roles" : "KAI 账号用途"}>
          <span className="home-v2-kicker">{copy.kicker}</span>
          <h1>{copy.title}</h1>
          <p>{copy.description}</p>
          <div className="auth-role-guide">
            <article><Key size={21}/><div><strong>{t("auth.role.buyer", "买家账号")}</strong><span>{t("auth.role.buyerDesc", "管理 SSH 公钥、服务器租约和续费")}</span></div></article>
            <article><HardDrives size={21}/><div><strong>{t("auth.role.supplier", "商家账号")}</strong><span>{t("auth.role.supplierDesc", "登记服务器、安装 Agent 并查看租约")}</span></div></article>
            <article><ShieldCheck size={21}/><div><strong>{t("auth.role.admin", "管理员账号")}</strong><span>{t("auth.role.adminDesc", "审核商家、服务器和平台状态")}</span></div></article>
          </div>
        </section>
        <section className="auth-page__form" aria-label={locale === "en" ? "Account sign in and registration" : "账号登录与注册"}>
          {mode === "login" || mode === "register" ? <AuthPanel mode={mode} /> : <PasswordRecoveryPanel mode={mode} />}
        </section>
      </main>
      <footer className="auth-page__footer"><span>{locale === "en" ? "Secure session · CSRF protection · Up to 14 days signed in" : "安全会话 · CSRF 防护 · 最长 14 天登录状态"}</span><Link href="/">{t("auth.backMarket", "返回算力市场")}</Link></footer>
    </div>
  );
}
