"use client";

import Link from "next/link";
import { CaretDown, Gear, HardDrives, House, List, Receipt, SignOut, Storefront, Wallet, X } from "@phosphor-icons/react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Brand } from "@/components/brand";
import { UiSettings } from "@/components/ui-settings";
import { AuthUser, getCurrentUser, logoutCurrentUser } from "@/lib/api";
import { useI18n } from "@/components/locale-root";

const navigation = [
  { key: "nav.home", label: "首页", href: "/" },
  { key: "nav.market", label: "算力市场", href: "/market" },
  { key: "nav.trends", label: "算力行情", href: "/market/trends" },
  { key: "nav.community", label: "算力社区", href: "/community" },
  { key: "nav.supplierApply", label: "商家入驻", href: "/supplier/apply" },
  { key: "nav.download", label: "下载 App", href: "/download" },
];

function isNavigationActive(pathname: string, href: string) {
  if (pathname === href) return true;
  if (href === "/" || !pathname.startsWith(`${href}/`)) return false;
  return !navigation.some((candidate) => candidate.href !== href && candidate.href.startsWith(`${href}/`) && (pathname === candidate.href || pathname.startsWith(`${candidate.href}/`)));
}

function consoleHref(user: AuthUser) {
  if (user.role === "admin") return "/admin";
  if (user.role === "supplier") return "/supplier";
  return "/account";
}

export function SiteHeader({ authMode = "auto" }: { authMode?: "auto" | "guest" }) {
  const { locale, t } = useI18n();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(authMode !== "guest");
  const consoleLabel = user?.role === "admin" ? t("nav.adminConsole", "管理控制台") : user?.role === "supplier" ? t("nav.supplierConsole", "商家后台") : t("nav.personalCenter", "个人中心");

  useEffect(() => {
    if (authMode === "guest") {
      setUser(null);
      setAuthLoading(false);
      return;
    }
    getCurrentUser().then(({ user: currentUser }) => setUser(currentUser)).catch(() => setUser(null)).finally(() => setAuthLoading(false));
  }, [authMode]);

  useEffect(() => {
    setOpen(false);
    setAccountOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  async function logout() {
    try {
      await logoutCurrentUser();
      setUser(null);
      setAccountOpen(false);
      window.location.assign("/");
    } catch {
      window.location.assign("/account/settings");
    }
  }

  return <header className="site-header">
    <div className="site-header__inner">
      <Brand />
      <nav className="site-nav" aria-label="主导航">
        {navigation.map((item) => {
          const active = isNavigationActive(pathname, item.href);
          return <Link aria-current={active ? "page" : undefined} href={item.href} key={item.key} onClick={() => setOpen(false)}>{t(item.key, item.label)}</Link>;
        })}
      </nav>
      <div className="site-header__actions">
        <UiSettings compact />
        {authLoading ? <span className="auth-nav-placeholder" aria-label={locale === "en" ? "Loading account status" : "正在读取登录状态"}/> : user ? <>
          <Link className="primary-link" href={consoleHref(user)}>{consoleLabel}</Link>
          <div className="account-menu">
            <button type="button" aria-label={t("nav.openAccount", "打开账户快捷菜单")} aria-expanded={accountOpen} onClick={() => setAccountOpen((value) => !value)}><span>{user.display_name.slice(0, 1).toUpperCase()}</span><CaretDown size={13}/></button>
            {accountOpen && <div>
              <strong>{user.display_name}<small>{consoleLabel}</small></strong>
              {user.role === "personal" && <>
                <Link href="/account"><House size={15}/>{t("nav.accountOverview", "账户总览")}</Link>
                <Link href="/account/orders"><Receipt size={15}/>{t("nav.orders", "我的订单")}</Link>
                <Link href="/account/assets"><HardDrives size={15}/>{t("nav.assets", "个人资产")}</Link>
                <Link href="/account/wallet"><Wallet size={15}/>{t("nav.wallet", "钱包与流水")}</Link>
              </>}
              {user.role === "supplier" && <>
                <Link href="/supplier"><Storefront size={15}/>{t("nav.supplierOverview", "商家总览")}</Link>
                <Link href="/supplier/orders"><Receipt size={15}/>{t("nav.deliveryOrders", "交付订单")}</Link>
                <Link href="/account"><House size={15}/>{t("nav.personalAccount", "个人账户")}</Link>
              </>}
              {user.role === "admin" && <Link href="/admin"><House size={15}/>{t("nav.adminOverview", "管理总览")}</Link>}
              {user.role !== "admin" && <Link href="/account/settings"><Gear size={15}/>{t("nav.accountSecurity", "账户与安全")}</Link>}
              <button type="button" onClick={() => void logout()}><SignOut size={14}/>{t("nav.logout", "退出登录")}</button>
            </div>}
          </div>
        </> : <><Link className="text-button" href="/register">{t("nav.register", "注册")}</Link><Link className="primary-link" href="/login">{t("nav.login", "登录 KAI")}</Link></>}
        <button className="mobile-menu-button" type="button" aria-label={open ? (locale === "en" ? "Close menu" : "关闭菜单") : (locale === "en" ? "Open menu" : "打开菜单")} aria-expanded={open} aria-controls="site-mobile-drawer" onClick={() => setOpen((value) => !value)}>{open ? <X size={20}/> : <List size={20}/>}</button>
      </div>
    </div>
    {open && <div className="site-mobile-overlay">
      <button className="site-mobile-backdrop" type="button" aria-label={locale === "en" ? "Close menu" : "关闭菜单"} onClick={() => setOpen(false)}/>
      <aside id="site-mobile-drawer" className="site-mobile-drawer" role="dialog" aria-modal="true" aria-label={locale === "en" ? "Site navigation" : "网站导航"}>
        <header><Brand/><button type="button" aria-label={locale === "en" ? "Close menu" : "关闭菜单"} onClick={() => setOpen(false)}><X size={20}/></button></header>
        <nav aria-label={locale === "en" ? "Mobile navigation" : "移动导航"}>
          {navigation.map((item) => {
            const active = isNavigationActive(pathname, item.href);
            return <Link aria-current={active ? "page" : undefined} className={active ? "active" : ""} href={item.href} key={item.key}>{t(item.key, item.label)}</Link>;
          })}
        </nav>
        <footer>
          <div className="site-mobile-settings"><UiSettings/></div>
          {user ? <>
            <Link href={consoleHref(user)}>{consoleLabel}</Link>
            {user.role !== "admin" && <Link href="/account/settings">{t("nav.accountSecurity", "账户与安全")}</Link>}
            <button type="button" onClick={() => void logout()}><SignOut size={16}/>{t("nav.logout", "退出登录")}</button>
          </> : <><Link href="/register">{t("nav.register", "注册")}</Link><Link className="site-mobile-primary" href="/login">{t("nav.login", "登录 KAI")}</Link></>}
        </footer>
      </aside>
    </div>}
  </header>;
}
