"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowRight, CreditCard, LockKey, ShieldCheck } from "@phosphor-icons/react";
import { getPaymentCredential, type PaymentCredential } from "@/lib/integration-api";

const channelNames: Record<string, string> = {
  alipay_pc_direct: "支付宝电脑支付",
  alipay_wap: "支付宝手机支付",
  wx_wap: "微信 H5 支付",
  upacp_pc: "银联网关支付",
  upacp_wap: "银联手机支付",
};

export function PingxxCheckout() {
  const params = useParams<{ paymentNo: string }>();
  const paymentNo = params.paymentNo;
  const [credential, setCredential] = useState<PaymentCredential | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getPaymentCredential(paymentNo)
      .then(setCredential)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "支付凭据读取失败"));
  }, [paymentNo]);

  async function pay() {
    if (!credential) return;
    setBusy(true);
    setError("");
    try {
      const module = await import("pingpp-js");
      module.default.createPayment(JSON.stringify(credential.charge), (result, sdkError) => {
        if (result === "success") {
          window.location.assign(credential.return_url);
          return;
        }
        if (result === "cancel") setError("支付已取消，你可以重新发起支付。 ");
        else setError(sdkError?.msg || sdkError?.extra || "未能调起 Ping++ 收银台");
        setBusy(false);
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ping++ SDK 加载失败");
      setBusy(false);
    }
  }

  return <main className="pingxx-checkout">
    <section className="pingxx-checkout__card">
      <header><span><ShieldCheck size={18} /> KAI SECURE CHECKOUT</span><b>{credential?.livemode ? "正式支付" : "Ping++ 模拟测试"}</b></header>
      <div className="pingxx-checkout__body">
        <div className="pingxx-checkout__mark"><CreditCard size={30} /></div>
        <p>PAYMENT / {paymentNo}</p>
        <h1>{credential ? channelNames[credential.channel] || credential.channel : "正在准备安全支付…"}</h1>
        <span>{credential?.livemode ? "支付结果以 Ping++ 验签回调为准。" : "这是 Ping++ Test 环境，不会产生真实资金变动。模拟页面点击支付后，仍须等待服务端回调确认。"}</span>
        <button type="button" disabled={!credential || busy} onClick={() => void pay()}>{busy ? "正在打开收银台…" : "继续支付"}<ArrowRight size={18} /></button>
        <small><LockKey size={14} /> 前端结果不会直接开通服务器，只有服务端验签并查单成功后才会交付 SSH 权限。</small>
        {error && <div className="commerce-error">{error}</div>}
      </div>
      <footer><Link href={credential?.return_url || "/account/orders"}>返回订单</Link><span>POWERED BY PING++</span></footer>
    </section>
  </main>;
}
