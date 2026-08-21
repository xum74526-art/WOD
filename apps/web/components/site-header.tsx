"use client";

import Link from "next/link";
import { CaretDown, List, SignOut, X } from "@phosphor-icons/react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Brand } from "@/components/brand";
import { UiSettings } from "@/components/ui-settings";
import { AuthUser, getCurrentUser, logoutCurrentUser } from "@/lib/api";

const navigation = [
  { label: "首页", href: "/" },
  { label: "算力市场", href: "/market" },
  { label: "算力行情", href: "/market/trends" },
  { label: "算力社区", href: "/community" },
  { label: "求购", href: "/requests" },
  { label: "商家入驻", href: "/supplier/apply" },
  { label: "下载 App", href: "/download" },
];

function isNavigationActive(pathname: string, href: string) {
  if (pathname === href) return true;
  if (href === "/" || !pathname.startsWith(`${href}/`)) return false;
  return !navigation.some((candidate) => (
    candidate.href !== href
    && candidate.href.startsWith(`${href}/`)
    && (pathname === candidate.href || pathname.startsWith(`${candidate.href}/`))
  ));
}

function consoleHref(user: AuthUser) {
  if (user.role === "admin") return "/admin";
  if (user.role === "supplier") return "/supplier";
  return "/account";
}

export function SiteHeader({ authMode = "auto" }: { authMode?: "auto" | "guest" }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(authMode !== "guest");
  useEffect(() => {
    if (authMode === "guest") {
      setUser(null);
      setAuthLoading(false);
      return;
    }
    getCurrentUser()
      .then(({ user: currentUser }) => setUser(currentUser))
      .catch(() => setUser(null))
      .finally(() => setAuthLoading(false));
  }, [authMode]);
  async function logout() {
    try {
      await logoutCurrentUser();
      setUser(null); setAccountOpen(false); window.location.assign("/");
    } catch {
      window.location.assign("/account/settings");
    }
  }
  return (
    <header className={`site-header ${open ? "site-header--open" : ""}`}>
      <div className="site-header__inner">
        <Brand />
        <nav className="site-nav" aria-label="主导航">
          {navigation.map((item) => {
            const active = isNavigationActive(pathname, item.href);
            return <Link aria-current={active ? "page" : undefined} href={item.href} key={item.label} onClick={() => setOpen(false)}>{item.label}</Link>;
          })}
        </nav>
        <div className="site-header__actions">
          <UiSettings compact />
          {authLoading ? <span className="auth-nav-placeholder" aria-label="正在读取登录状态" /> : user ? <><Link className="primary-link" href={consoleHref(user)}>控制台</Link><div className="account-menu"><button type="button" aria-expanded={accountOpen} onClick={() => setAccountOpen((value) => !value)}><span>{user.display_name.slice(0, 1).toUpperCase()}</span><CaretDown size={13} /></button>{accountOpen && <div><strong>{user.display_name}</strong>{user.role === "personal" && <Link href="/account/settings">账户与安全</Link>}{user.role === "supplier" && <><Link href="/supplier">商家后台</Link><Link href="/account">账户与安全</Link></>}{user.role === "admin" && <Link href="/admin">管理控制台</Link>}<button type="button" onClick={() => void logout()}><SignOut size={14} />退出登录</button></div>}</div></> : <><Link className="text-button" href="/register">注册</Link><Link className="primary-link" href="/login">登录 KAI</Link></>}
          <button className="mobile-menu-button" type="button" aria-label={open ? "关闭菜单" : "打开菜单"} aria-expanded={open} onClick={() => setOpen((value) => !value)}>
            {open ? <X size={20} /> : <List size={20} />}
          </button>
        </div>
      </div>
    </header>
  );
}
