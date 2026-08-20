"use client";

import { FormEvent, useEffect, useState } from "react";
import { ArrowClockwise, Coins, LockKey, Receipt } from "@phosphor-icons/react";
import { createPaymentIntent, getWalletSnapshot, type WalletSnapshot } from "@/lib/integration-api";
import { ProviderState } from "@/components/provider-state";

const statusLabel: Record<string, string> = {
  created: "已创建",
  provider_pending: "等待支付",
  succeeded: "已成功",
  failed: "失败",
  cancelled: "已取消",
  expired: "已过期",
};

export function PaymentWorkspace() {
  const [data, setData] = useState<WalletSnapshot | null>(null);
  const [amount, setAmount] = useState("100");
  const [channel, setChannel] = useState("alipay_pc_direct");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    setError("");
    getWalletSnapshot().then(setData).catch((reason) => setError(reason instanceof Error ? reason.message : "钱包服务暂时不可用"));
  }
  useEffect(load, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const intent = await createPaymentIntent(amount, "CNY", channel);
      if (intent.checkout_url) window.location.assign(intent.checkout_url);
      else load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "暂时无法创建支付单");
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <section className="workspace-page"><div className="workspace-skeleton" aria-label="正在读取钱包" />{error && <div className="commerce-error">{error}</div>}</section>;
  return (
    <section className="workspace-page integration-workspace">
      <div className="workspace-page__head integration-head"><div><p>ACCOUNT / WALLET</p><h1>钱包与流水</h1><span>余额来自双分录账本；支付结果只能由服务商回调确认。</span></div><button onClick={load}><ArrowClockwise size={16} />刷新</button></div>
      <ProviderState descriptor={data.provider} />
      <div className="integration-balance-grid">
        {data.balances.map((balance) => <article key={balance.currency}><span>{balance.currency}</span><small>可用余额</small><strong>{balance.available}</strong><em>冻结 {balance.frozen}</em></article>)}
        <article className="integration-ledger-card"><LockKey size={23} /><small>账本模式</small><strong>双分录</strong><em>借贷不平衡的交易会被拒绝</em></article>
      </div>
      <div className="integration-columns">
        <form className="integration-action-card" onSubmit={submit}>
          <header><Coins size={21} /><div><h2>账户充值</h2><p>通过 Ping++ Test 或 Live 环境创建支付凭据。</p></div></header>
          <label><span>充值金额（CNY）</span><input type="number" min="0.01" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} disabled={!data.provider.configured} /></label>
          <label><span>支付方式</span><select value={channel} onChange={(event) => setChannel(event.target.value)} disabled={!data.provider.configured}><option value="alipay_pc_direct">支付宝电脑支付</option><option value="alipay_wap">支付宝手机支付</option><option value="wx_wap">微信 H5 支付</option><option value="upacp_pc">银联网关支付</option></select></label>
          <button className="commerce-primary" disabled={!data.provider.configured || busy}>{busy ? "正在创建…" : data.provider.configured ? "前往支付" : "支付服务未配置"}</button>
          <p>未配置状态不会扣款，也不会创建成功或待支付记录。</p>
        </form>
        <section className="integration-ledger">
          <header><Receipt size={20} /><div><h2>支付记录</h2><p>最多显示最近 20 条真实记录。</p></div></header>
          {data.payment_intents.length ? data.payment_intents.map((intent) => <article key={intent.id}><div><small>{intent.payment_no}</small><strong>{intent.currency} {intent.amount}</strong></div><span>{statusLabel[intent.status] || intent.status}</span></article>) : <div className="commerce-empty"><Receipt size={23} /><strong>暂无支付记录</strong></div>}
        </section>
      </div>
      {error && <div className="commerce-error">{error}</div>}
    </section>
  );
}
