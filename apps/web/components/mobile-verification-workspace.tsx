"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { CheckCircle, IdentificationCard, ImageSquare, LockKey, ShieldCheck, WarningCircle } from "@phosphor-icons/react";
import { errorMessage } from "@/lib/commerce-ui";
import { getVerification, submitVerification, uploadVerificationPhotos, type VerificationInfo } from "@/lib/mobile-business-api";

const statusText: Record<string, string> = { unverified: "未认证", pending: "审核中", verified: "已认证", rejected: "已驳回" };
const ocrText: Record<string, string> = { not_started: "等待证件照片", processing: "识别处理中", matched: "资料匹配", review_required: "需要人工复核", error: "识别失败", unavailable: "等待人工审核" };
const acceptedPhotoTypes = new Set(["image/jpeg", "image/png", "image/webp"]);

export function MobileVerificationWorkspace() {
  const [info, setInfo] = useState<VerificationInfo | null>(null);
  const [form, setForm] = useState({ real_name: "", id_card: "", sensitive_consent: false });
  const [front, setFront] = useState<File | null>(null);
  const [back, setBack] = useState<File | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(async () => { setError(""); try { setInfo(await getVerification()); } catch (reason) { setError(errorMessage(reason)); } }, []);
  useEffect(() => { void load(); }, [load]);

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy("identity"); setError("");
    try { const updated = await submitVerification(form); setInfo((current) => ({ ...current, ...updated })); setForm({ real_name: "", id_card: "", sensitive_consent: false }); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(""); }
  }

  function selectPhoto(side: "front" | "back", file?: File) {
    if (!file) { side === "front" ? setFront(null) : setBack(null); return; }
    if (!acceptedPhotoTypes.has(file.type)) { setError("身份证照片仅支持 JPG、PNG 或 WebP"); return; }
    if (file.size > 5 * 1024 * 1024) { setError("单张身份证照片不能超过 5MB"); return; }
    setError(""); side === "front" ? setFront(file) : setBack(file);
  }

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!front && !back) { setError("请至少选择一张身份证照片"); return; }
    setBusy("photos"); setError("");
    try { const updated = await uploadVerificationPhotos(front, back); setInfo((current) => ({ ...current, ...updated })); setFront(null); setBack(null); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(""); }
  }

  const status = info?.status || "unverified";
  const identityLocked = ["pending", "verified"].includes(status);
  const photoLocked = status === "verified";
  const photoReady = Boolean(info?.consent_recorded) && !photoLocked;
  return <section className="workspace-page mobile-verification">
    <div className="workspace-page__head"><p>ACCOUNT / IDENTITY</p><h1>实名认证</h1><span>查看认证资料、证件照片和 OCR 预检状态。</span></div>
    {error && <div className="commerce-error">{error}</div>}
    {!info ? <div className="workspace-skeleton"/> : <div className="mobile-verification-layout">
      <aside className={`mobile-verification-status status-${status}`}><div>{status === "verified" ? <CheckCircle size={38}/> : status === "rejected" ? <WarningCircle size={38}/> : <ShieldCheck size={38}/>}<span><small>VERIFICATION STATUS</small><strong>{statusText[status] || status}</strong></span></div><dl><div><dt>认证姓名</dt><dd>{info.real_name || "未提交"}</dd></div><div><dt>证件号码</dt><dd>{info.id_card_masked || "未提交"}</dd></div><div><dt>敏感信息授权</dt><dd>{info.consent_recorded ? "已记录" : "未记录"}</dd></div><div><dt>证件正面</dt><dd>{info.front_photo_uploaded ? "已上传" : "未上传"}</dd></div><div><dt>证件反面</dt><dd>{info.back_photo_uploaded ? "已上传" : "未上传"}</dd></div><div><dt>OCR 预检</dt><dd>{ocrText[info.ocr_status || ""] || info.ocr_status || "未开始"}</dd></div></dl>{info.ocr_message && <p className="ocr-message">{info.ocr_message}</p>}{info.reject_reason && <p>{info.reject_reason}</p>}</aside>
      <div className="verification-form-stack">
        <form className="mobile-business-form verification-form" onSubmit={submit}><header><IdentificationCard size={22}/><div><small>IDENTITY APPLICATION</small><h2>{status === "rejected" ? "重新提交认证" : "提交认证资料"}</h2></div></header><label>真实姓名<input autoComplete="name" value={form.real_name} onChange={(event) => setForm({ ...form, real_name: event.target.value })} disabled={identityLocked} required/></label><label>身份证号<input autoComplete="off" value={form.id_card} onChange={(event) => setForm({ ...form, id_card: event.target.value.toUpperCase() })} disabled={identityLocked} required/></label><label className="mobile-consent"><input type="checkbox" checked={form.sensitive_consent} onChange={(event) => setForm({ ...form, sensitive_consent: event.target.checked })} disabled={identityLocked}/><span>我同意平台为本地文字识别和人工审核处理上述敏感个人信息。</span></label><button className="commerce-primary" disabled={busy === "identity" || identityLocked || !form.sensitive_consent}>{busy === "identity" ? "提交中…" : status === "verified" ? "认证已完成" : status === "pending" ? "资料审核中" : "提交认证资料"}</button><p><LockKey size={14}/> Web 不保存证件号码；后端返回时只显示脱敏结果。</p></form>
        <form className="mobile-business-form verification-photo-form" onSubmit={upload}><header><ImageSquare size={22}/><div><small>ID PHOTO / OCR</small><h2>身份证照片</h2></div></header><div className="verification-photo-grid"><label><span>人像面（正面）</span><input type="file" accept="image/jpeg,image/png,image/webp" disabled={!photoReady} onChange={(event) => selectPhoto("front", event.target.files?.[0])}/><small>{front?.name || (info.front_photo_uploaded ? "后端已有照片" : "JPG / PNG / WebP，最大 5MB")}</small></label><label><span>国徽面（反面）</span><input type="file" accept="image/jpeg,image/png,image/webp" disabled={!photoReady} onChange={(event) => selectPhoto("back", event.target.files?.[0])}/><small>{back?.name || (info.back_photo_uploaded ? "后端已有照片" : "JPG / PNG / WebP，最大 5MB")}</small></label></div><button className="commerce-primary" disabled={busy === "photos" || !photoReady || (!front && !back)}>{busy === "photos" ? "上传与识别中…" : photoLocked ? "认证已完成" : !info.consent_recorded ? "请先提交认证资料" : "安全上传证件照片"}</button><p><ShieldCheck size={14}/> 图片由 BFF 直接转发到私有存储，不生成公开访问地址。</p></form>
      </div>
    </div>}
  </section>;
}
