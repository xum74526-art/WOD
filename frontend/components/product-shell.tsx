"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowSquareOut,
  Bell,
  ChartLine,
  ChatCircleText,
  ClipboardText,
  Coins,
  Cube,
  FileLock,
  Gavel,
  Gear,
  House,
  IdentificationCard,
  Key,
  MapPin,
  Receipt,
  SidebarSimple,
  ShieldCheck,
  SignOut,
  Storefront,
  Users,
  UsersThree,
  Wallet,
} from "@phosphor-icons/react";
import { Brand } from "@/components/brand";
import { UiSettings } from "@/components/ui-settings";
import { ApiError, getCurrentUser, type AuthUser } from "@/lib/api";
import { loginHref } from "@/lib/auth-navigation";

type WorkspaceVariant = "account" | "supplier" | "admin";

const buyerNav = [
  { label: "买家总览", href: "/account", icon: House },
  { label: "服务器市场", href: "/market", icon: Storefront },
  { label: "我的服务器", href: "/account/leases", icon: Cube },
  { label: "采购订单", href: "/account/orders", icon: Receipt },
  { label: "SSH 公钥", href: "/account/ssh-keys", icon: Key },
  { label: "钱包与流水", href: "/account/wallet", icon: Wallet },
  { label: "买家通知", href: "/account/notifications", icon: Bell },
  { label: "采购争议", href: "/account/disputes", icon: Gavel },
  { label: "账户与安全", href: "/account/settings", icon: Gear },
];

const supplierAccountNav = [
  { label: "账户资料", href: "/account/settings", icon: Gear },
  { label: "实名认证", href: "/account/verification", icon: IdentificationCard },
  { label: "私有文件", href: "/account/files", icon: FileLock },
  { label: "站内通知", href: "/account/notifications", icon: Bell },
  { label: "协作团队", href: "/account/teams", icon: UsersThree },
  { label: "API Key", href: "/account/api-keys", icon: Key },
];

const supplierNav = [
  { label: "经营总览", href: "/supplier", icon: House },
  { label: "服务器商品", href: "/supplier/resources", icon: Cube },
  { label: "服务器与 Agent", href: "/supplier/servers", icon: ShieldCheck },
  { label: "服务器租约", href: "/supplier/leases", icon: Key },
  { label: "租赁订单", href: "/supplier/orders", icon: Receipt },
  { label: "收益与提现", href: "/supplier/revenue", icon: Wallet },
  { label: "商家资料", href: "/supplier/settings", icon: Gear },
];

const adminNav = [
  { label: "运营总览", href: "/admin", icon: House },
  { label: "实名认证", href: "/admin/kyc", icon: IdentificationCard },
  { label: "商家准入", href: "/admin/suppliers", icon: ShieldCheck },
  { label: "服务器审核", href: "/admin/resources", icon: Cube },
  { label: "退款处理", href: "/admin/refunds", icon: Receipt },
  { label: "提现结算", href: "/admin/withdrawals", icon: Coins },
  { label: "争议仲裁", href: "/admin/disputes", icon: Gavel },
  { label: "内容治理", href: "/admin/moderation", icon: ChatCircleText },
];

function redirectForRole(user: AuthUser, variant: WorkspaceVariant) {
  if (variant === "admin" && user.role !== "admin") return user.role === "supplier" ? "/supplier" : "/account";
  if (variant === "supplier" && user.role !== "supplier") return user.role === "admin" ? "/admin" : "/supplier/apply";
  if (variant === "account" && user.role === "admin") return "/admin";
  return null;
}

export function ProductShell({ children, variant = "account" }: { children: React.ReactNode; variant?: WorkspaceVariant }) {
  const pathname = usePathname();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const [navCollapsed, setNavCollapsed] = useState(false);

  useEffect(() => {
    let active = true;
    getCurrentUser().then(({ user: current }) => {
      if (!active) return;
      const destination = redirectForRole(current, variant);
      if (destination) {
        window.location.replace(destination);
        return;
      }
      setUser(current);
      setReady(true);
    }).catch((reason) => {
      if (!active) return;
      setUser(null);
      if (reason instanceof ApiError && reason.status === 401) window.location.replace(loginHref(pathname));
    });
    return () => { active = false; };
  }, [variant]);

  if (!ready || !user) {
    return <div className={`workspace-shell workspace-shell--${variant}`}><main className="workspace-gate" aria-label="正在验证工作台权限"><span /></main></div>;
  }

  const navigation = variant === "admin" ? adminNav : variant === "supplier" ? supplierNav : user.role === "supplier" ? supplierAccountNav : buyerNav;
  const workspaceName = variant === "admin" ? "管理控制台" : variant === "supplier" ? "商家后台" : user.role === "supplier" ? "账户中心" : "买家中心";
  const roleName = variant === "admin" ? "PLATFORM ADMIN" : variant === "supplier" ? "APPROVED SUPPLIER" : user.role === "supplier" ? "SUPPLIER ACCOUNT" : "COMPUTE BUYER";
  const isActive = (href: string) => pathname === href || (!["/account", "/supplier", "/admin"].includes(href) && pathname.startsWith(`${href}/`));

  return (
    <div className={`workspace-shell workspace-shell--${variant}${navCollapsed ? " workspace-shell--collapsed" : ""}`}>
      <a className="skip-to-content" href="#workspace-content">跳到主要内容</a>
      <aside className="workspace-sidebar">
        <Brand />
        <div className="workspace-identity"><span>{roleName}</span><strong>{workspaceName}</strong><small>{user.display_name}</small></div>
        <nav aria-label={`${workspaceName}导航`}>
          {navigation.map((item) => {
            const Icon = item.icon;
            return <Link className={isActive(item.href) ? "active" : ""} href={item.href} key={item.href}><Icon size={18} /><span>{item.label}</span></Link>;
          })}
        </nav>
        <div className="workspace-sidebar__foot">
          {variant === "account" && user.role === "personal" && <Link href="/supplier/apply"><Storefront size={18} />申请成为商家</Link>}
          {variant === "account" && user.role === "supplier" && <Link href="/supplier"><Storefront size={18} />返回商家后台</Link>}
          {variant === "supplier" && <Link href="/account"><Users size={18} />账户与安全</Link>}
          {variant === "admin" && <Link href="/"><Storefront size={18} />查看公开网站</Link>}
          <Link href="/login"><SignOut size={18} />退出或更换账号</Link>
          <button type="button" onClick={() => setNavCollapsed((value) => !value)} aria-expanded={!navCollapsed} title={navCollapsed ? "展开导航" : "收起导航"}><SidebarSimple size={18}/><span>{navCollapsed ? "展开导航" : "收起导航"}</span></button>
        </div>
      </aside>
      <div className="workspace-main">
        <header className="workspace-topbar">
          <div><strong>KAI {workspaceName}</strong><span>已安全连接</span></div>
          <div><Link href="/"><ArrowSquareOut size={17} /><span>公开网站</span></Link><UiSettings compact /></div>
        </header>
        <header className="workspace-mobile-head"><Brand /><span>{workspaceName}</span><UiSettings compact /></header>
        <nav className="workspace-mobile-nav" aria-label={`${workspaceName}移动导航`}>
          {navigation.map((item) => <Link className={isActive(item.href) ? "active" : ""} href={item.href} key={item.href}>{item.label}</Link>)}
        </nav>
        <main id="workspace-content" tabIndex={-1}>{children}</main>
      </div>
    </div>
  );
}
