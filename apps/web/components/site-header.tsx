"use client";

import Link from "next/link";
import { AndroidLogo, AppleLogo, ArrowRight, CaretDown, DownloadSimple, Gear, HardDrives, House, List, Phone, Receipt, SignOut, Storefront, Wallet, X } from "@phosphor-icons/react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Brand } from "@/components/brand";
import { UiSettings } from "@/components/ui-settings";
import { AuthUser, getCurrentUser, logoutCurrentUser } from "@/lib/api";
import { useI18n } from "@/components/locale-root";

const navigation = [
  { key: "nav.home", label: "首页", href: "/" },
  { key: "nav.market", label: "算力市场", href: "/market" },
  { key: "nav.trends", label: "算力行情", href: "/trend" },
  { key: "nav.community", label: "算力社区", href: "/community" },
  { key: "nav.supplierApply", label: "商家入驻", href: "/supplier/apply" },
  { key: "nav.download", label: "下载 App", href: "/download" },
];

const androidApkUrl = process.env.NEXT_PUBLIC_KAI_ANDROID_APK_URL?.trim();
const mobileDownloadUrl = androidApkUrl || "https://wod.kai.com/download";

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
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(authMode !== "guest");
  const downloadRef = useRef<HTMLDivElement>(null);
  const downloadCloseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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
    setDownloadOpen(false);
  }, [pathname]);

  useEffect(() => () => {
    if (downloadCloseTimerRef.current) clearTimeout(downloadCloseTimerRef.current);
  }, []);

  useEffect(() => {
    if (!downloadOpen) return;
    const close = (event: PointerEvent) => {
      if (!downloadRef.current?.contains(event.target as Node)) setDownloadOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDownloadOpen(false);
    };
    document.addEventListener("pointerdown", close);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", close);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [downloadOpen]);

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

  function openDownloadPopover() {
    if (downloadCloseTimerRef.current) clearTimeout(downloadCloseTimerRef.current);
    downloadCloseTimerRef.current = null;
    setDownloadOpen(true);
  }

  function scheduleDownloadPopoverClose() {
    if (downloadCloseTimerRef.current) clearTimeout(downloadCloseTimerRef.current);
    downloadCloseTimerRef.current = setTimeout(() => {
      setDownloadOpen(false);
      downloadCloseTimerRef.current = null;
    }, 180);
  }

  return <header className="site-header">
    <div className="site-header__inner">
      <Brand />
      <nav className="site-nav" aria-label="主导航">
        {navigation.map((item) => {
          const active = isNavigationActive(pathname, item.href);
          if (item.href === "/download") return <div
            className="download-nav"
            key={item.key}
            ref={downloadRef}
            onMouseEnter={openDownloadPopover}
            onMouseLeave={scheduleDownloadPopoverClose}
          >
            <Link
              className="download-nav__trigger"
              href="/download"
              aria-current={active ? "page" : undefined}
              aria-expanded={downloadOpen}
              aria-haspopup="dialog"
            >
              <DownloadSimple size={16}/>{t(item.key, item.label)}
            </Link>
            {downloadOpen && <section className="download-popover" role="dialog" aria-label={locale === "en" ? "Download KAI App" : "下载北斗 kai App"} onMouseEnter={openDownloadPopover}>
              <div className="download-popover__scan">
                <header><Phone size={21}/><strong>{locale === "en" ? "Mobile" : "手机版"}</strong></header>
                <p>{locale === "en" ? "Scan to open the download page" : "扫码打开手机下载页"}</p>
                <div className="download-popover__qr"><QRCodeSVG value={mobileDownloadUrl} size={124} level="M" bgColor="#ffffff" fgColor="#102b29" marginSize={1}/></div>
              </div>
              <div className="download-popover__direct">
                <header><DownloadSimple size={21}/><div><strong>{locale === "en" ? "App clients" : "客户端"}</strong><small>{locale === "en" ? "Choose a version for your device" : "选择适合设备的版本"}</small></div></header>
                <article>
                  <span className="download-popover__platform-icon"><AndroidLogo size={25} weight="fill"/></span>
                  <div><strong>Android</strong><small>Android 8.0+</small></div>
                  {androidApkUrl ? <a href={androidApkUrl} download>{locale === "en" ? "Download" : "立即下载"}</a> : <em>{locale === "en" ? "Preparing" : "正在准备"}</em>}
                </article>
                <article>
                  <span className="download-popover__platform-icon is-apple"><AppleLogo size={25} weight="fill"/></span>
                  <div><strong>iPhone</strong><small>iOS 13+</small></div>
                  <em>{locale === "en" ? "Coming soon" : "即将上线"}</em>
                </article>
              </div>
              <Link className="download-popover__more" href="/download">{locale === "en" ? "See more download options" : "点击查看更多下载内容"}<ArrowRight size={14}/></Link>
            </section>}
          </div>;
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
                <Link href="/supplier/resources"><HardDrives size={15}/>{t("nav.supplierProducts", "算力商品")}</Link>
                <Link href="/supplier/orders"><Receipt size={15}/>{t("nav.deliveryOrders", "交付订单")}</Link>
                <Link href="/account"><House size={15}/>{t("nav.personalAccount", "个人账户")}</Link>
              </>}
              {user.role === "admin" && <Link href="/admin"><House size={15}/>{t("nav.adminOverview", "管理总览")}</Link>}
              {user.role !== "admin" && <Link href="/account/settings"><Gear size={15}/>{t("nav.accountSecurity", "账户与安全")}</Link>}
              <button type="button" onClick={() => void logout()}><SignOut size={14}/>{t("nav.logout", "退出登录")}</button>
            </div>}
          </div>
        </> : <><Link className="text-button" href="/register">{t("nav.register", "注册")}</Link><Link className="primary-link" href="/login">{t("nav.login", "登录")}</Link></>}
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
            {user.role === "supplier" && <Link href="/supplier/resources">{t("nav.supplierProducts", "算力商品")}</Link>}
            {user.role === "supplier" && <Link href="/supplier/orders">{t("nav.deliveryOrders", "交付订单")}</Link>}
            {user.role !== "admin" && <Link href="/account/settings">{t("nav.accountSecurity", "账户与安全")}</Link>}
            <button type="button" onClick={() => void logout()}><SignOut size={16}/>{t("nav.logout", "退出登录")}</button>
          </> : <><Link href="/register">{t("nav.register", "注册")}</Link><Link className="site-mobile-primary" href="/login">{t("nav.login", "登录")}</Link></>}
        </footer>
      </aside>
    </div>}
  </header>;
}
