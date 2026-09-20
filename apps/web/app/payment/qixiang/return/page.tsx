"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { ArrowClockwise, Wallet } from "@phosphor-icons/react";
import { SiteHeader } from "@/components/site-header";

export default function QixiangPaymentReturnPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/account/wallet");
  }, [router]);

  return (
    <div className="site-page public-v2">
      <SiteHeader />
      <main className="public-data-page">
        <div className="data-empty" role="status" aria-live="polite">
          <ArrowClockwise size={28} />
          <strong>正在核验支付结果</strong>
          <p>即将返回钱包并向平台查询订单状态。到账结果只以服务端验签和钱包入账记录为准。</p>
          <Link className="primary-link" href="/account/wallet"><Wallet size={17} />立即返回钱包</Link>
        </div>
      </main>
    </div>
  );
}
