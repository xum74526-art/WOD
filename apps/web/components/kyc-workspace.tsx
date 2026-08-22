"use client";

import { useEffect, useState } from "react";
import { IdentificationCard, LockKey, ShieldCheck } from "@phosphor-icons/react";
import { getKycSnapshot, submitManualKyc, type KycSnapshot } from "@/lib/integration-api";
import { ProviderState } from "@/components/provider-state";

const labels: Record<string, string> = {
  unverified: "未认证",
  draft: "资料草稿",
  pending: "审核中",
  approved: "已认证",
  rejected: "未通过",
  expired: "已过期",
};

export function KycWorkspace() {
  const [data, setData] = useState<KycSnapshot | null>(null);
  const [kind, setKind] = useState<"individual" | "business">("individual");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [legalName, setLegalName] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [representative, setRepresentative] = useState("");
  const [accepted, setAccepted] = useState(false);
  useEffect(() => { getKycSnapshot().then(setData).catch((reason) => setError(reason instanceof Error ? reason.message : "实名认证服务暂时不可用")); }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await submitManualKyc({
        verification_type: kind,
        country_code: "CN",
        legal_name: legalName,
        identifier_type: kind === "business" ? "business_registration" : "national_id",
        identifier_number: identifier,
        representative_name: kind === "business" ? representative : undefined,
        declaration_accepted: accepted,
      });
      setData(await getKycSnapshot());
      setIdentifier("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "暂时无法提交实名认证");
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <section className="workspace-page"><div className="workspace-skeleton" aria-label="正在读取认证状态" />{error && <div className="commerce-error">{error}</div>}</section>;
  return (
    <section className="workspace-page integration-workspace">
      <div className="workspace-page__head"><p>ACCOUNT / VERIFICATION</p><h1>实名认证</h1><span>提交主体身份信息后由平台人工核验；证件号码加密保存，不要求上传证件照片。</span></div>
      <ProviderState descriptor={data.provider} />
      <div className="kyc-console">
        <article className="kyc-status-card"><IdentificationCard size={30} /><div><small>当前状态</small><strong>{labels[data.status] || data.status}</strong><span>{data.application?.review_note || "成为商家前需要完成主体实名认证。"}</span>{data.application?.subject && <dl className="kyc-subject-summary"><div><dt>主体名称</dt><dd>{data.application.subject.legal_name}</dd></div><div><dt>证件号码</dt><dd>{data.application.subject.identifier_number}</dd></div></dl>}</div></article>
        <form className="integration-action-card" onSubmit={submit}>
          <header><ShieldCheck size={22} /><div><h2>提交认证资料</h2><p>管理员审核通过后，才可批准商家入驻与申请提现。</p></div></header>
          <div className="kyc-kind-switch"><button type="button" className={kind === "individual" ? "active" : ""} onClick={() => setKind("individual")}>个人认证</button><button type="button" className={kind === "business" ? "active" : ""} onClick={() => setKind("business")}>企业认证</button></div>
          <label><span>{kind === "business" ? "企业名称" : "真实姓名"}</span><input required minLength={2} maxLength={128} value={legalName} onChange={(event) => setLegalName(event.target.value)} placeholder={kind === "business" ? "营业执照上的企业全称" : "身份证件上的姓名"}/></label>
          <label><span>{kind === "business" ? "统一社会信用代码" : "身份证件号码"}</span><input required minLength={6} maxLength={64} autoComplete="off" value={identifier} onChange={(event) => setIdentifier(event.target.value)} placeholder="仅用于人工核验，加密保存"/></label>
          {kind === "business" && <label><span>法定代表人</span><input required minLength={2} maxLength={64} value={representative} onChange={(event) => setRepresentative(event.target.value)} placeholder="营业执照登记的法定代表人"/></label>}
          <label className="kyc-declaration"><input type="checkbox" checked={accepted} onChange={(event) => setAccepted(event.target.checked)}/><span>我确认以上资料真实有效，并授权北斗 kai 用于商家准入与结算身份核验。</span></label>
          <button className="commerce-primary" type="submit" disabled={busy || !accepted || data.status === "pending" || data.status === "approved"}>{busy ? "正在加密提交…" : data.status === "pending" ? "等待管理员审核" : data.status === "approved" ? "认证已通过" : "提交人工审核"}</button>
        </form>
      </div>
      <div className="integration-safety-note"><LockKey size={20} /><div><strong>身份信息保护</strong><span>买家和其他商家无法查看认证信息；用户端仅显示证件末四位，完整号码只对管理员审核队列可见。</span></div></div>
      {error && <div className="commerce-error">{error}</div>}
    </section>
  );
}
