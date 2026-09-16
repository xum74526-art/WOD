"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowSquareOut,
  Bank,
  Bell,
  ChatCircleText,
  ClipboardText,
  Coins,
  Cube,
  Gavel,
  Gear,
  Gift,
  HardDrives,
  House,
  IdentificationCard,
  List,
  MapPin,
  Receipt,
  SidebarSimple,
  ShieldCheck,
  SignOut,
  Storefront,
  Ticket,
  TrendUp,
  Users,
  UsersThree,
  Wallet,
  X,
} from "@phosphor-icons/react";
import { Brand } from "@/components/brand";
import { UiSettings } from "@/components/ui-settings";
import { ApiError, getCurrentUser, logoutCurrentUser, type AuthUser } from "@/lib/api";
import { locationReturnPath, loginHref } from "@/lib/auth-navigation";
import { useI18n } from "@/components/locale-root";

type WorkspaceVariant = "account" | "supplier" | "admin";

const buyerNav = [
  { label: "买家总览", href: "/account", icon: House },
  { label: "算力市场", href: "/market", icon: Storefront },
  { label: "个人资产", href: "/account/assets", icon: HardDrives },
  { label: "设备托管", href: "/account/hosting", icon: Cube },
  { label: "采购订单", href: "/account/orders", icon: Receipt },
  { label: "求购与报价", href: "/account/requests", icon: UsersThree },
  { label: "钱包与流水", href: "/account/wallet", icon: Wallet },
  { label: "收益与返佣", href: "/account/revenue", icon: TrendUp },
  { label: "优惠券", href: "/account/coupons", icon: Ticket },
  { label: "邀请记录", href: "/account/referrals", icon: Gift },
  { label: "银行卡", href: "/account/bank-accounts", icon: Bank },
  { label: "实名认证", href: "/account/verification", icon: IdentificationCard },
  { label: "通知中心", href: "/account/notifications", icon: Bell },
  { label: "在线客服", href: "/support", icon: ChatCircleText },
  { label: "地址管理", href: "/account/addresses", icon: MapPin },
  { label: "账户设置", href: "/account/settings", icon: Gear },
];

const supplierAccountNav = [
  { label: "账户总览", href: "/account", icon: House },
  { label: "个人资产", href: "/account/assets", icon: HardDrives },
  { label: "设备托管", href: "/account/hosting", icon: Cube },
  { label: "采购订单", href: "/account/orders", icon: Receipt },
  { label: "钱包与流水", href: "/account/wallet", icon: Wallet },
  { label: "收益与返佣", href: "/account/revenue", icon: TrendUp },
  { label: "银行卡", href: "/account/bank-accounts", icon: Bank },
  { label: "优惠券", href: "/account/coupons", icon: Ticket },
  { label: "账户资料", href: "/account/settings", icon: Gear },
  { label: "实名认证", href: "/account/verification", icon: IdentificationCard },
  { label: "站内通知", href: "/account/notifications", icon: Bell },
  { label: "在线客服", href: "/support", icon: ChatCircleText },
  { label: "地址管理", href: "/account/addresses", icon: MapPin },
];

const supplierNav = [
  { label: "经营总览", href: "/supplier", icon: House },
  { label: "需求市场", href: "/supplier/requests", icon: ClipboardText },
  { label: "算力商品", href: "/supplier/resources", icon: Cube },
  { label: "交付订单", href: "/supplier/orders", icon: Receipt },
  { label: "收益与提现", href: "/supplier/revenue", icon: Wallet },
  { label: "经营统计", href: "/supplier/analytics", icon: TrendUp },
  { label: "商家返佣", href: "/supplier/rebates", icon: Gift },
  { label: "商家资料", href: "/supplier/settings", icon: Gear },
];

const adminNav = [
  { label: "运营总览", href: "/admin", icon: House },
  { label: "需求管理", href: "/admin/requests", icon: ClipboardText },
  { label: "端口数据", href: "/admin/data", icon: UsersThree },
  { label: "实名认证", href: "/admin/kyc", icon: IdentificationCard },
  { label: "商家入驻审核", href: "/admin/suppliers", icon: ShieldCheck },
  { label: "订单争议", href: "/admin/disputes", icon: Gavel },
  { label: "银行卡复核", href: "/admin/bank-cards", icon: Bank },
  { label: "提现结算", href: "/admin/withdrawals", icon: Coins },
];

const englishNavigation: Record<string, string> = {
  "买家总览": "Buyer Overview", "算力市场": "Compute Market", "个人资产": "My Assets", "设备托管": "Device Hosting", "采购订单": "Orders", "求购与报价": "Requests & Quotes", "钱包与流水": "Wallet & Ledger", "收益与返佣": "Earnings & Rebates", "优惠券": "Coupons", "邀请记录": "Referrals", "银行卡": "Bank Cards", "实名认证": "Identity Verification", "通知中心": "Notifications", "在线客服": "Support", "地址管理": "Addresses", "账户设置": "Account Settings", "账户总览": "Account Overview", "账户资料": "Account Profile", "站内通知": "Notifications", "经营总览": "Operations Overview", "需求市场": "Request Market", "算力商品": "Compute Products", "交付订单": "Delivery Orders", "收益与提现": "Revenue & Withdrawals", "经营统计": "Analytics", "商家返佣": "Supplier Rebates", "商家资料": "Supplier Profile", "运营总览": "Admin Overview", "需求管理": "Request Management", "端口数据": "Platform Data", "商家入驻审核": "Merchant Admission", "订单争议": "Order Disputes", "银行卡复核": "Bank Card Review", "提现结算": "Withdrawal Settlement",
};

function redirectForRole(user: AuthUser, variant: WorkspaceVariant) {
  if (variant === "supplier" && user.role !== "supplier") return user.role === "admin" ? "/admin" : "/supplier/apply";
  if (variant === "account" && user.role === "admin") return "/admin";
  return null;
}

export function ProductShell({ children, variant = "account" }: { children: React.ReactNode; variant?: WorkspaceVariant }) {
  const { locale, t } = useI18n();
  const pathname = usePathname();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [gateFailed, setGateFailed] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setReady(false);
    setGateFailed(false);
    getCurrentUser(loadAttempt > 0).then(async ({ user: current }) => {
      if (!active) return;
      if (variant === "admin" && current.role !== "admin") { window.location.replace("/"); return; }
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
      if (reason instanceof ApiError && reason.status === 401) {
        window.location.replace(loginHref(locationReturnPath(window.location)));
        return;
      }
      setGateFailed(true);
      setReady(true);
    });
    return () => { active = false; };
  }, [loadAttempt, variant]);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  async function logout() {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      await logoutCurrentUser();
    } catch {
      // The BFF still clears this device's HttpOnly cookie on an upstream
      // failure, so local sign-out must finish without an unhandled rejection.
    } finally {
      setUser(null);
      setMobileNavOpen(false);
      window.location.replace("/login");
    }
  }

  useEffect(() => {
    if (!mobileNavOpen) return;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileNavOpen(false);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [mobileNavOpen]);

  if (gateFailed) {
    return <div className={`workspace-shell workspace-shell--${variant}`}><main className="workspace-gate workspace-gate--error" role="alert"><div className="workspace-gate__error"><strong>{locale === "en" ? "Workspace unavailable" : "工作台暂时无法加载"}</strong><p>{locale === "en" ? "Check your network connection and try again." : "请检查网络连接后重试。"}</p><div><button type="button" onClick={() => setLoadAttempt((value) => value + 1)}>{locale === "en" ? "Try again" : "重新加载"}</button><Link href="/">{locale === "en" ? "Back to home" : "返回首页"}</Link></div></div></main></div>;
  }

  if (!ready || !user) {
    return <div className={`workspace-shell workspace-shell--${variant}`}><main className="workspace-gate" aria-label={t("workspace.verifying", "正在验证工作台权限")}><span /></main></div>;
  }

  const navigation = variant === "admin" ? adminNav : variant === "supplier" ? supplierNav : user.role === "supplier" ? supplierAccountNav : buyerNav;
  const workspaceName = variant === "admin" ? t("workspace.admin", "管理控制台") : variant === "supplier" ? t("workspace.supplier", "商家后台") : user.role === "supplier" ? (locale === "en" ? "Account Center" : "账户中心") : t("workspace.buyer", "买家中心");
  const roleName = variant === "admin" ? "PLATFORM ADMIN" : variant === "supplier" ? "APPROVED SUPPLIER" : user.role === "supplier" ? "SUPPLIER ACCOUNT" : "COMPUTE BUYER";
  const isActive = (href: string) => pathname === href || (!["/account", "/supplier", "/admin"].includes(href) && pathname.startsWith(`${href}/`));

  return (
    <div className={`workspace-shell workspace-shell--${variant}${navCollapsed ? " workspace-shell--collapsed" : ""}`}>
      <a className="skip-to-content" href="#workspace-content">{t("accessibility.skipToContent", "跳到主要内容")}</a>
      <aside className="workspace-sidebar">
        <Brand />
        <div className="workspace-identity"><span>{roleName}</span><strong>{workspaceName}</strong><small>{user.display_name}</small></div>
        <nav aria-label={t("workspace.navigation", "{name}导航", { name: workspaceName })}>
          {navigation.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.href);
            return <Link aria-current={active ? "page" : undefined} className={active ? "active" : ""} href={item.href} key={item.href}><Icon size={18}/><span>{locale === "en" ? englishNavigation[item.label] || item.label : item.label}</span></Link>;
          })}
        </nav>
        <div className="workspace-sidebar__foot">
          {variant === "account" && user.role === "personal" && <Link href="/supplier/apply"><Storefront size={18}/>{t("nav.supplierApply", "申请成为商家")}</Link>}
          {variant === "account" && user.role === "supplier" && <Link href="/supplier"><Storefront size={18}/>{locale === "en" ? "Back to Supplier Console" : "返回商家后台"}</Link>}
          {variant === "supplier" && <Link href="/account"><Users size={18}/>{locale === "en" ? "Buyer Workspace" : "买家工作台"}</Link>}
          {variant === "admin" && <Link href="/"><Storefront size={18}/>{locale === "en" ? "View Public Site" : "查看公开网站"}</Link>}
          <button type="button" disabled={loggingOut} onClick={() => void logout()}><SignOut size={18}/><span aria-live="polite">{loggingOut ? (locale === "en" ? "Signing out…" : "正在退出…") : locale === "en" ? "Sign out or switch account" : "退出或更换账号"}</span></button>
          <button type="button" onClick={() => setNavCollapsed((value) => !value)} aria-expanded={!navCollapsed} title={navCollapsed ? (locale === "en" ? "Expand navigation" : "展开导航") : (locale === "en" ? "Collapse navigation" : "收起导航")}><SidebarSimple size={18}/><span>{navCollapsed ? (locale === "en" ? "Expand navigation" : "展开导航") : (locale === "en" ? "Collapse navigation" : "收起导航")}</span></button>
        </div>
      </aside>
      <div className="workspace-main">
        <header className="workspace-topbar">
          <div><strong>{locale === "en" ? "KAI" : "北斗 kai"} {workspaceName}</strong><span>{t("workspace.connected", "已连接统一业务平台")}</span></div>
          <div><Link href="/"><ArrowSquareOut size={17}/><span>{t("workspace.publicSite", "公开网站")}</span></Link><UiSettings compact/></div>
        </header>
        <header className="workspace-mobile-head">
          <button
            className="workspace-mobile-menu"
            type="button"
            aria-label={locale === "en" ? "Open workspace navigation" : "打开工作台导航"}
            aria-expanded={mobileNavOpen}
            aria-controls="workspace-mobile-drawer"
            onClick={() => setMobileNavOpen(true)}
          ><List size={21}/></button>
          <Brand />
          <span>{workspaceName}</span>
          <UiSettings compact />
        </header>
        {mobileNavOpen && <div className="workspace-mobile-overlay">
          <button className="workspace-mobile-backdrop" type="button" aria-label={locale === "en" ? "Close navigation" : "关闭导航"} onClick={() => setMobileNavOpen(false)} />
          <aside id="workspace-mobile-drawer" className="workspace-mobile-drawer" role="dialog" aria-modal="true" aria-label={t("workspace.navigation", "{name}导航", { name: workspaceName })}>
            <header>
              <Brand />
              <button type="button" aria-label={locale === "en" ? "Close navigation" : "关闭导航"} onClick={() => setMobileNavOpen(false)}><X size={20}/></button>
            </header>
            <div className="workspace-mobile-identity"><span>{roleName}</span><strong>{workspaceName}</strong><small>{user.display_name}</small></div>
            <nav>
              {navigation.map((item) => {
                const Icon = item.icon;
                const active = isActive(item.href);
                return <Link aria-current={active ? "page" : undefined} className={active ? "active" : ""} href={item.href} key={item.href}><Icon size={19}/><span>{locale === "en" ? englishNavigation[item.label] || item.label : item.label}</span></Link>;
              })}
            </nav>
            <footer>
              <Link href="/"><ArrowSquareOut size={18}/><span>{t("workspace.publicSite", "公开网站")}</span></Link>
              <button type="button" disabled={loggingOut} onClick={() => void logout()}><SignOut size={18}/><span aria-live="polite">{loggingOut ? (locale === "en" ? "Signing out…" : "正在退出…") : locale === "en" ? "Sign out or switch account" : "退出或更换账号"}</span></button>
            </footer>
          </aside>
        </div>}
        <main id="workspace-content" tabIndex={-1}>{children}</main>
      </div>
    </div>
  );
}
