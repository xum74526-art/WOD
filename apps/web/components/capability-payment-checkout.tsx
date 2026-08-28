"use client";

import Link from "next/link";
import { PingxxCheckout } from "@/components/pingxx-checkout";
import { SiteHeader } from "@/components/site-header";
import { usePlatformCapabilities } from "@/lib/use-platform-capabilities";

export function CapabilityPaymentCheckout() {
  const { capabilities, loading } = usePlatformCapabilities();
  if (loading) {
    return <div className="site-page public-v2"><SiteHeader/><main className="public-data-page"><div className="data-empty">正在确认支付服务状态…</div></main></div>;
  }
  if (capabilities.direct_trade_enabled === true && capabilities.payment_enabled === true) {
    return <PingxxCheckout/>;
  }
  return <div className="site-page public-v2"><SiteHeader/><main className="public-data-page"><div className="data-empty"><strong>在线支付暂未开放</strong><p>当前仅支持提交算力需求并由工作人员人工联系确认方案。</p><Link className="primary-link" href="/account/requests?create=1">提交需求</Link><Link className="outline-link" href="/account/wallet">查看历史记录</Link></div></main></div>;
}
