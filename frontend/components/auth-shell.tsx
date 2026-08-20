import Link from "next/link";
import { HardDrives, Key, ShieldCheck } from "@phosphor-icons/react/dist/ssr";
import { AuthPanel } from "@/components/auth-panel";
import { PasswordRecoveryPanel } from "@/components/password-recovery-panel";
import { SiteHeader } from "@/components/site-header";

type AuthShellProps = {
  mode: "login" | "register" | "forgot" | "reset";
};

export function AuthShell({ mode }: AuthShellProps) {
  const copy = mode === "login"
    ? { kicker: "KAI ACCOUNT ACCESS", title: "登录后，继续管理你的服务器", description: "买家查看租约与 SSH 连接，商家管理服务器与 Agent，管理员处理平台审核。" }
    : mode === "register"
      ? { kicker: "JOIN KAI", title: "从一把 SSH 公钥开始租用服务器", description: "创建账号后添加自己的 SSH 公钥，购买服务器时长并直接获得连接命令。" }
      : { kicker: "ACCOUNT SECURITY", title: "安全恢复你的 KAI 账号", description: "通过注册邮箱更新登录凭证，恢复后继续管理服务器和租约。" };

  return (
    <div className="site-page auth-page">
      <SiteHeader authMode="guest" />
      <main className="auth-page__main">
        <section className="auth-page__intro" aria-label="KAI 账号用途">
          <span className="home-v2-kicker">{copy.kicker}</span>
          <h1>{copy.title}</h1>
          <p>{copy.description}</p>
          <div className="auth-role-guide">
            <article><Key size={21}/><div><strong>买家账号</strong><span>管理 SSH 公钥、服务器租约和续费</span></div></article>
            <article><HardDrives size={21}/><div><strong>商家账号</strong><span>登记服务器、安装 Agent 并查看租约</span></div></article>
            <article><ShieldCheck size={21}/><div><strong>管理员账号</strong><span>审核商家、服务器和平台状态</span></div></article>
          </div>
        </section>
        <section className="auth-page__form" aria-label="账号登录与注册">
          {mode === "login" || mode === "register" ? <AuthPanel mode={mode} /> : <PasswordRecoveryPanel mode={mode} />}
        </section>
      </main>
      <footer className="auth-page__footer"><span>安全会话 · CSRF 防护 · 最长 14 天登录状态</span><Link href="/">返回服务器市场</Link></footer>
    </div>
  );
}
