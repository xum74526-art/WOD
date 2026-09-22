"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, CalendarDots, Coins, Cpu, Gauge, TrendUp } from "@phosphor-icons/react";
import { getMobileAsset, type MobileAsset } from "@/lib/mobile-business-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";
import { assetStatusLabel } from "@/lib/asset-status";
import { useI18n } from "@/components/locale-root";
import { formatFinancialAmount } from "@/lib/financial-format";

const amount = (value: unknown) => formatFinancialAmount(value as number | string | null | undefined);

export function MobileAssetDetail({ id }: { id: number }) {
  const { t } = useI18n();
  const [item, setItem] = useState<MobileAsset | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { getMobileAsset(id).then(setItem).catch((reason) => setError(errorMessage(reason))); }, [id]);
  const holding = item?.purchase_type === "holding";
  const currentValue = holding ? item?.current_price ?? item?.value : item?.value;
  return <section className="workspace-page mobile-asset-detail">
    <div className="workspace-page__head">
      <Link href="/account/assets"><ArrowLeft size={16}/>返回个人资产</Link>
      <p>ACCOUNT / ASSET #{id}</p>
      <h1>{item?.product_name || item?.gpu_model || "资产详情"}</h1>
      <span>{holding ? "查看持有资产估值、可出售状态和真实盈亏。" : "查看使用资产、到期返佣和服务期限。"}</span>
    </div>
    {error && <div className="commerce-error">{error}</div>}
    {!item && !error ? <div className="workspace-skeleton"/> : item && <>
      <div className="mobile-data-spine">
        <article><small>{holding ? "当前估值" : "资产价值"}</small><strong>{amount(currentValue)}</strong><span>卡时</span></article>
        <article><small>{holding ? "买入价值" : "待结算购买返佣"}</small><strong>{amount(holding ? item.buy_price : item.rebate_info?.pending_rebate)}</strong><span>卡时</span></article>
        <article><small>{holding ? "持有盈亏" : "已结算购买返佣"}</small><strong>{amount(holding ? item.pnl : item.rebate_info?.settled_rebate)}</strong><span>卡时</span></article>
        <article><small>{holding ? "盈亏比例" : "剩余时间"}</small><strong>{holding ? amount(item.pnl_pct) : item.remaining_days ?? "—"}</strong><span>{holding ? "%" : "天"}</span></article>
      </div>
      <section className="mobile-record-panel asset-detail-facts">
        <header><Cpu size={20}/><div><small>ASSET FACTS</small><h2>资产信息</h2></div><b>{assetStatusLabel(item.status, item.purchase_type, t)}</b></header>
        <dl>
          <div><dt>GPU 型号</dt><dd>{item.gpu_model || "—"}</dd></div>
          <div><dt>设备数量</dt><dd>{item.quantity || 1} 台</dd></div>
          <div><dt>购买模式</dt><dd>{holding ? "持有并可出售" : "使用"}</dd></div>
          <div><dt><CalendarDots/>生效时间</dt><dd>{formatDate(item.start_at)}</dd></div>
          <div><dt><CalendarDots/>到期时间</dt><dd>{holding ? "长期持有" : formatDate(item.end_at)}</dd></div>
          <div><dt><Coins/>当前估值</dt><dd>{item.current_price == null ? holding ? "暂不可用" : amount(item.value) : amount(item.current_price)}</dd></div>
          <div><dt><TrendUp/>{holding ? "持有盈亏" : "到期返佣"}</dt><dd>{holding ? item.pnl == null ? "暂不可用" : `${item.pnl >= 0 ? "+" : ""}${amount(item.pnl)}` : amount(item.rebate_amount)}</dd></div>
        </dl>
        {item.trading_unavailable_reason && <div className="workspace-service-note"><Gauge size={17}/>{item.trading_unavailable_reason}</div>}
      </section>
    </>}
  </section>;
}
