"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowClockwise, ChartLine, Coins, Gear, Gift, HardDrives, Receipt, TrendUp } from "@phosphor-icons/react";
import { useI18n } from "@/components/locale-root";
import { errorMessage } from "@/lib/commerce-ui";
import { getSupplierProfile, getSupplierRebate, getSupplierRevenueBundle, getSupplierStats, getUserRebate, updateSupplierProfile, type RebateSummary, type SupplierProfile, type SupplierRebate, type SupplierRevenueRecord, type SupplierStats, type SupplierWallet } from "@/lib/mobile-business-api";
import { localizeRebateHint, rebateTierRange } from "@/lib/product-purchase";
import { usePlatformCapabilities } from "@/lib/use-platform-capabilities";

export type MobileSupplierSection = "revenue" | "analytics" | "rebates" | "settings";
const amount = (value: unknown) => {
  const n = Number(value || 0);
  return Number.isFinite(n) ? n.toFixed(2) : "0.00";
};
const date = (value?: string | null) => (value ? new Date(value).toLocaleDateString("zh-CN") : "—");

function SupplierRevenue() {
  const { capabilities } = usePlatformCapabilities();
  const withdrawalEntryEnabled = capabilities.direct_trade_enabled === true && capabilities.withdraw_enabled === true;
  const [wallet, setWallet] = useState<SupplierWallet | null>(null);
  const [rows, setRows] = useState<SupplierRevenueRecord[]>([]);
  const [error, setError] = useState("");
  const load = useCallback(
    () =>
      getSupplierRevenueBundle()
        .then(([a, b]) => {
          setWallet(a);
          setRows(b);
        })
        .catch((reason) => setError(errorMessage(reason))),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  if (!wallet && !error) return <div className="workspace-skeleton" />;
  return (
    <>
      {error && <div className="commerce-error">{error}</div>}
      <div className="mobile-data-spine supplier-spine">
        <article>
          <small>今日收益</small>
          <strong>{amount(wallet?.today_revenue)}</strong>
          <span>卡时</span>
        </article>
        <article>
          <small>可提现</small>
          <strong>{amount(wallet?.available)}</strong>
          <span>卡时</span>
        </article>
        <article>
          <small>待结算</small>
          <strong>{amount(wallet?.pending_amount)}</strong>
          <span>卡时</span>
        </article>
        <article>
          <small>累计已提现</small>
          <strong>{amount(wallet?.withdrawn)}</strong>
          <span>卡时</span>
        </article>
      </div>
      <section className="mobile-record-panel supplier-revenue-ledger">
        <header>
          <Receipt size={20} />
          <div>
            <small>SETTLEMENT LEDGER</small>
            <h2>订单收益明细</h2>
          </div>
          <button onClick={() => void load()}>
            <ArrowClockwise size={15} />
            刷新
          </button>
        </header>
        {rows.length ? (
          rows.map((row) => (
            <article key={row.order_no}>
              <span>
                <strong>{row.product_name}</strong>
                <small>
                  {row.buyer_name} · {row.order_no}
                </small>
              </span>
              <span>
                <strong>{row.status === "completed" ? `+${amount(row.net_income)}` : "待结算"}</strong>
                <small>
                  订单 {amount(row.amount)} · 服务费 {amount(row.service_fee)}
                </small>
              </span>
              <time>{date(row.created_at)}</time>
            </article>
          ))
        ) : (
          <div className="mobile-inline-empty">暂无订单收益记录</div>
        )}
      </section>
      {withdrawalEntryEnabled
        ? <div className="workspace-service-note">已结算的商家收益进入统一钱包。<Link className="primary-link" href="/account/wallet">前往钱包申请提现</Link></div>
        : <div className="workspace-service-note">新提现申请当前未开放；已结算收益和历史提现记录仍可在统一钱包查看。<Link className="outline-link" href="/account/wallet">查看钱包记录</Link></div>}
    </>
  );
}

function SupplierAnalytics() {
  const [data, setData] = useState<SupplierStats | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    getSupplierStats()
      .then(setData)
      .catch((reason) => setError(errorMessage(reason)));
  }, []);
  const max = useMemo(() => Math.max(1, ...(data?.revenue_trend || []).map((point) => Number(point.amount || 0))), [data]);
  if (!data && !error) return <div className="workspace-skeleton" />;
  const averageUtilization = (data?.device_stats || []).reduce((sum, item) => sum + Number(item.utilization || 0), 0) / Math.max(1, data?.device_stats.length || 0);
  return (
    <>
      {error && <div className="commerce-error">{error}</div>}
      <div className="mobile-data-spine">
        <article>
          <small>算力商品</small>
          <strong>{data?.total_products || 0}</strong>
          <span>个商品</span>
        </article>
        <article>
          <small>累计订单</small>
          <strong>{data?.total_orders || 0}</strong>
          <span>笔订单</span>
        </article>
        <article className={data?.attention_count ? "is-warning" : ""}>
          <small>需要关注</small>
          <strong>{data?.attention_count || 0}</strong>
          <span>台设备</span>
        </article>
        <article>
          <small>平均利用率</small>
          <strong>{amount(averageUtilization)}%</strong>
          <span>设备均值</span>
        </article>
      </div>
      <div className="mobile-service-columns">
        <section className="mobile-trend-panel">
          <header>
            <div>
              <small>REVENUE TREND</small>
              <h2>营收趋势</h2>
            </div>
            <ChartLine size={21} />
          </header>
          {data?.revenue_trend?.length ? (
            <div className="mobile-mini-bars">
              {data.revenue_trend.map((point, index) => (
                <span key={`${point.date}-${index}`}>
                  <i
                    style={{
                      height: `${Math.max(4, (Number(point.amount || 0) / max) * 100)}%`,
                    }}
                  />
                  <small>{point.date.slice(5)}</small>
                </span>
              ))}
            </div>
          ) : (
            <div className="mobile-inline-empty">暂无营收趋势</div>
          )}
        </section>
        <section className="supplier-utilization">
          <header>
            <HardDrives size={20} />
            <div>
              <small>DEVICE UTILIZATION</small>
              <h2>设备利用率</h2>
            </div>
          </header>
          {data?.device_stats?.length ? (
            data.device_stats.map((device, index) => (
              <article key={`${device.name}-${device.gpu_model}-${index}`}>
                <span>
                  <strong>{device.name}</strong>
                  <small>
                    {device.gpu_model} · {device.order_count} 个订单
                  </small>
                </span>
                <div>
                  <i>
                    <b
                      style={{
                        width: `${Math.min(100, Math.max(0, Number(device.utilization || 0)))}%`,
                      }}
                    />
                  </i>
                  <strong>{amount(device.utilization)}%</strong>
                </div>
              </article>
            ))
          ) : (
            <div className="mobile-inline-empty">暂无设备统计</div>
          )}
        </section>
      </div>
    </>
  );
}

function SupplierRebates() {
  const { locale, t } = useI18n();
  const [personal, setPersonal] = useState<RebateSummary | null>(null);
  const [supplier, setSupplier] = useState<SupplierRebate | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([getUserRebate(), getSupplierRebate()])
      .then(([personalSummary, supplierSummary]) => {
        setPersonal(personalSummary);
        setSupplier(supplierSummary);
      })
      .catch((reason) => setError(errorMessage(reason)));
  }, []);
  const personalTiers = personal?.tiers ?? [];
  const supplierTiers = supplier?.tiers ?? [];
  const personalHint = localizeRebateHint(personal?.next_tier_hint, locale)
    || t("rebate.personal.noHint", "当前没有新的等级提示。");
  const supplierHint = localizeRebateHint(supplier?.next_tier_hint, locale)
    || t("rebate.supplier.noHint", "当前没有新的等级提示。");
  const personalCap = Number(personal?.monthly_cap ?? 0);
  const supplierCap = Number(supplier?.monthly_cap ?? 0);
  const personalEntitled = Number(personal?.month_entitled ?? 0);
  const personalCapUsed = Number(personal?.cap_used ?? 0);
  const personalCapRemaining = Number(personal?.cap_remaining ?? 0);
  const supplierEntitled = Number(supplier?.month_entitled ?? 0);
  const supplierCapUsed = Number(supplier?.cap_used ?? 0);
  const supplierCapRemaining = Number(supplier?.cap_remaining ?? 0);
  if ((!personal || !supplier) && !error) return <div className="workspace-skeleton" />;
  return (
    <>
      {error && <div className="commerce-error">{error}</div>}
      <div className="mobile-data-spine">
        <article>
          <small>{t("rebate.personal.monthSpent", "本月个人购买")}</small>
          <strong>{amount(personal?.month_spent)}</strong>
          <span>{t("rebate.unit.cardHours", "卡时")}</span>
        </article>
        <article>
          <small>{t("rebate.personal.monthRebated", "本月个人购买返佣")}</small>
          <strong>{amount(personal?.month_rebated)}</strong>
          <span>{t("rebate.unit.cardHours", "卡时")}</span>
        </article>
        <article>
          <small>{t("rebate.supplier.monthSales", "本月已确认销售")}</small>
          <strong>{amount(supplier?.month_sales)}</strong>
          <span>{t("rebate.unit.cardHours", "卡时")}</span>
        </article>
        <article>
          <small>{t("rebate.supplier.monthRebated", "本月商家销售返佣")}</small>
          <strong>{amount(supplier?.month_rebated)}</strong>
          <span>{t("rebate.unit.cardHours", "卡时")}</span>
        </article>
      </div>
      <div className="mobile-service-columns rebate-program-columns">
        <section className="mobile-rebate-panel rebate-program-card">
          <header>
            <Gift size={20} />
            <div>
              <small>PERSONAL PURCHASE REBATE</small>
              <h2>{t("rebate.personal.title", "个人购买返佣")}</h2>
            </div>
          </header>
          <strong>{amount(personal?.current_rate)}%</strong>
          <span>{t("rebate.personal.currentTierLabel", "当前个人购买等级")}</span>
          <p>{t("rebate.personal.mechanism", "仅统计已确认交付的使用模式订单；等级按本月个人购买卡时总额计算，资产服务期结束后返佣入账。")}</p>
          <footer>{personalHint}<br/>{t("rebate.personal.summary", "待到期 {pending} · 本月应计 {entitled} · 已用额度 {used} · 剩余额度 {remaining} · 月度上限 {cap} 卡时", { pending: amount(personal?.pending_rebate), entitled: amount(personalEntitled), used: amount(personalCapUsed), remaining: amount(personalCapRemaining), cap: amount(personalCap) })}</footer>
        </section>
        <section className="mobile-rebate-panel rebate-program-card">
          <header>
            <TrendUp size={20} />
            <div>
              <small>SUPPLIER SALES REBATE</small>
              <h2>{t("rebate.supplier.title", "商家销售返佣")}</h2>
            </div>
          </header>
          <strong>{amount(supplier?.current_rate)}%</strong>
          <span>{t("rebate.supplier.currentTierLabel", "当前商家销售等级")}</span>
          <p>{t("rebate.supplier.mechanism", "返佣基数为本月已确认销售卡时总额，不是平台服务费；按销售总额乘当前等级比例计算。")}</p>
          <footer>{supplierHint}<br/>{t("rebate.supplier.summary", "预计返佣 {estimated} · 本月应计 {entitled} · 已用额度 {used} · 剩余额度 {remaining} · 月度上限 {cap} 卡时", { estimated: amount(supplier?.est_total_rebate), entitled: amount(supplierEntitled), used: amount(supplierCapUsed), remaining: amount(supplierCapRemaining), cap: amount(supplierCap) })}</footer>
        </section>
      </div>
      <div className="mobile-service-columns rebate-tier-columns">
        <section className="supplier-tier-panel">
          <header><Gift size={20}/><div><small>PERSONAL TIERS</small><h2>{t("rebate.personal.tiers", "个人购买等级")}</h2></div></header>
          {personalTiers.map((tier, index) => <article className={Number(personal?.current_rate) === Number(tier.rate) ? "active" : ""} key={`${tier.rate}-${index}`}><strong>{tier.rate}%</strong><span>{rebateTierRange(personalTiers, index, locale)} {t("rebate.unit.cardHours", "卡时")}</span>{Number(personal?.current_rate) === Number(tier.rate) && <b>{t("rebate.current", "当前")}</b>}</article>)}
        </section>
        <section className="supplier-tier-panel">
          <header><TrendUp size={20}/><div><small>SUPPLIER TIERS</small><h2>{t("rebate.supplier.tiers", "商家销售等级")}</h2></div></header>
          {supplierTiers.map((tier, index) => <article className={Number(supplier?.current_rate) === Number(tier.rate) ? "active" : ""} key={`${tier.rate}-${index}`}><strong>{tier.rate}%</strong><span>{rebateTierRange(supplierTiers, index, locale)} {t("rebate.unit.cardHours", "卡时")}</span>{Number(supplier?.current_rate) === Number(tier.rate) && <b>{t("rebate.current", "当前")}</b>}</article>)}
        </section>
      </div>
    </>
  );
}

function SupplierSettings() {
  const [profile, setProfile] = useState<SupplierProfile | null>(null);
  const [form, setForm] = useState({
    company_name: "",
    contact: "",
    phone: "",
    region: "",
    desc: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    getSupplierProfile()
      .then((value) => {
        setProfile(value);
        setForm({
          company_name: value.company_name || "",
          contact: value.contact || "",
          phone: value.phone || "",
          region: value.region || "",
          desc: value.desc || "",
        });
      })
      .catch((reason) => setError(errorMessage(reason)));
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const value = await updateSupplierProfile(form);
      setProfile(value);
      setSaved(true);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }
  if (!profile && !error) return <div className="workspace-skeleton" />;
  return (
    <>
      {error && <div className="commerce-error">{error}</div>}
      <div className="mobile-service-columns settings-layout">
        <aside className="supplier-profile-card">
          <Gear size={27} />
          <small>STORE PROFILE</small>
          <h2>{profile?.company_name || "商家资料"}</h2>
          <span className={`status-${profile?.status}`}>{profile?.status || "unknown"}</span>
          <p>资料修改后提交统一业务平台；审核状态不会由 Web 单独改变。</p>
          {saved && <b>资料已保存</b>}
        </aside>
        <form className="mobile-business-form" onSubmit={submit}>
          <header>
            <Gear size={20} />
            <div>
              <small>BUSINESS IDENTITY</small>
              <h2>编辑店铺资料</h2>
            </div>
          </header>
          <label>
            公司或店铺名称
            <input value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} required />
          </label>
          <div className="form-pair">
            <label>
              联系人
              <input value={form.contact} onChange={(e) => setForm({ ...form, contact: e.target.value })} required />
            </label>
            <label>
              联系电话
              <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} required />
            </label>
          </div>
          <label>
            所在地区
            <input value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} />
          </label>
          <label>
            店铺介绍
            <textarea value={form.desc} onChange={(e) => setForm({ ...form, desc: e.target.value })} />
          </label>
          <button className="commerce-primary" disabled={busy}>
            {busy ? "保存中…" : "保存店铺资料"}
          </button>
        </form>
      </div>
    </>
  );
}

const headers: Record<MobileSupplierSection, { eyebrow: string; title: string; description: string; icon: typeof Coins }> = {
  revenue: {
    eyebrow: "SUPPLIER / SETTLEMENT",
    title: "收益与提现",
    description: "查看订单收益、待结算和可提现余额。",
    icon: Coins,
  },
  analytics: {
    eyebrow: "SUPPLIER / OPERATIONS",
    title: "经营统计",
    description: "查看设备利用率、订单量、营收趋势和需要关注的设备。",
    icon: ChartLine,
  },
  rebates: {
    eyebrow: "SUPPLIER / REBATES",
    title: "商家返佣",
    description: "查看当前返佣阶梯、本月进度和预计返佣。",
    icon: Gift,
  },
  settings: {
    eyebrow: "SUPPLIER / PROFILE",
    title: "商家资料",
    description: "维护店铺、联系人和地区资料。",
    icon: Gear,
  },
};

export function MobileSupplierOperations({ section }: { section: MobileSupplierSection }) {
  const { t } = useI18n();
  const header = headers[section];
  const Icon = header.icon;
  return (
    <section className={`workspace-page mobile-supplier-ops mobile-supplier-ops--${section}`}>
      <div className="mobile-ops-head">
        <div>
          <p>{header.eyebrow}</p>
          <h1>{section === "rebates" ? t("rebate.center.title", "返佣中心") : header.title}</h1>
          <span>{section === "rebates" ? t("rebate.center.description", "分别查看个人购买返佣与商家销售返佣，两套等级和进度独立计算。") : header.description}</span>
        </div>
        <Icon size={34} weight="thin" />
      </div>
      {section === "revenue" ? <SupplierRevenue /> : section === "analytics" ? <SupplierAnalytics /> : section === "rebates" ? <SupplierRebates /> : <SupplierSettings />}
    </section>
  );
}
