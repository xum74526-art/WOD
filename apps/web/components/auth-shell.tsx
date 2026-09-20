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
  const { t } = useI18n();
  const copy = mode === "login"
    ? {
      kicker: t("auth.login.kicker", "算力星图账号登录"),
      title: t("auth.intro.login", "连接你的算力资源"),
      description: t("auth.intro.loginDescription", "一个账号进入买家、商家与平台工作台，按角色显示对应功能。"),
    }
    : mode === "register"
      ? {
        kicker: t("auth.register.kicker", "创建你的账号"),
        title: t("auth.intro.register", "创建你的算力星图账号"),
        description: t("auth.intro.registerDescription", "注册后添加 SSH 公钥，即可租用算力并管理连接。"),
      }
      : {
        kicker: t("auth.security.kicker", "账号安全"),
        title: t("auth.intro.forgot", "找回算力星图账号"),
        description: t("auth.intro.securityDescription", "通过已绑定邮箱或 KAI 身份找回算力星图账号并重置密码，继续管理算力资源和租约。"),
      };

  return (
    <div className="site-page public-v2 auth-page">
      <SiteHeader authMode="guest" />
      <main className="auth-page__main">
        <section className="auth-page__intro" aria-label={t("auth.rolesLabel", "算力星图账号用途")}>
          <span className="home-v2-kicker">{copy.kicker}</span>
          <h1>{copy.title}</h1>
          <p>{copy.description}</p>
          <div className="auth-role-guide">
            <article><Key size={21}/><div><strong>{t("auth.role.buyer", "买家账号")}</strong><span>{t("auth.role.buyerDesc", "管理 SSH 公钥、服务器租约和续费")}</span></div></article>
            <article><HardDrives size={21}/><div><strong>{t("auth.role.supplier", "商家账号")}</strong><span>{t("auth.role.supplierDesc", "登记服务器、安装 Agent 并查看租约")}</span></div></article>
            <article><ShieldCheck size={21}/><div><strong>{t("auth.role.admin", "管理员账号")}</strong><span>{t("auth.role.adminDesc", "审核商家、服务器和平台状态")}</span></div></article>
          </div>
        </section>
        <section className="auth-page__form" aria-label={t("auth.formLabel", "账号登录与注册")}>
          {mode === "login" || mode === "register" ? <AuthPanel mode={mode} /> : <PasswordRecoveryPanel mode={mode} />}
        </section>
      </main>
      <footer className="auth-page__footer"><span>{t("auth.footerSecurity", "安全会话 · CSRF 防护 · 最长 14 天登录状态")}</span><Link href="/">{t("auth.backMarket", "返回算力市场")}</Link></footer>
    </div>
  );
}
