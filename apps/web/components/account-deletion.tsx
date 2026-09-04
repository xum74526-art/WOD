"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";
import { useI18n } from "@/components/locale-root";
import { ApiError } from "@/lib/api";
import { loginHref } from "@/lib/auth-navigation";
import { getAccountDeletionEligibility, getAccountDeletionStatus, submitAccountDeletion, verifyAccountDeletion } from "@/lib/account-deletion-api";
import {
  clearDeletionReceipt, deletionRevokesNormalSession, newDeletionReceipt, readDeletionReceipt,
  saveDeletionReceipt, submitDeletionWithRecovery,
  type AccountDeletionEligibility, type AccountDeletionStatus, type AccountDeletionVerification, type DeletionReceipt,
} from "@/lib/account-deletion-flow";
import styles from "@/components/account-deletion.module.css";

export function AccountDeletion() {
  const { locale } = useI18n();
  const en = locale === "en";
  const [eligibility, setEligibility] = useState<AccountDeletionEligibility | null>(null);
  const [guest, setGuest] = useState(false);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [password, setPassword] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [verification, setVerification] = useState<AccountDeletionVerification | null>(null);
  const [receipt, setReceipt] = useState<DeletionReceipt | null>(null);
  const [status, setStatus] = useState<AccountDeletionStatus | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const [retryConfirmation, setRetryConfirmation] = useState(false);

  const applyStatus = useCallback((result: AccountDeletionStatus, sourceTicket: string) => {
    setStatus(result);
    setUncertain(false);
    setRetryConfirmation(false);
    if (deletionRevokesNormalSession(result)) {
      setPassword("");
      setVerification(null);
      setEligibility(null);
    }
    if (result.status === "completed") {
      try { clearDeletionReceipt(window.localStorage, sourceTicket); } catch { /* Still show the confirmed backend result. */ }
      setReceipt((current) => current?.ticket === sourceTicket ? null : current);
    }
  }, []);

  const loadEligibility = useCallback(async () => {
    setBusy(true); setError(""); setGuest(false);
    try { setEligibility(await getAccountDeletionEligibility()); }
    catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) setGuest(true);
      else setError(reason instanceof Error ? reason.message : "无法检查注销条件，请稍后重试。");
    } finally { setBusy(false); }
  }, []);

  useEffect(() => {
    let active = true;
    let saved: DeletionReceipt | null = null;
    try { saved = readDeletionReceipt(window.localStorage); } catch { /* Submission separately requires a saved recovery receipt. */ }
    if (!saved) { void loadEligibility(); return () => { active = false; }; }
    const savedTicket = saved.ticket;
    setReceipt(saved);
    getAccountDeletionStatus(savedTicket)
      .then((result) => { if (active) applyStatus(result, savedTicket); })
      .catch((reason) => {
        if (!active) return;
        setUncertain(true);
        setError(reason instanceof Error ? reason.message : "暂时无法查询注销结果。");
      })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [applyStatus, loadEligibility]);

  const checkStatus = useCallback(async () => {
    if (!receipt) return;
    setBusy(true); setError("");
    try { applyStatus(await getAccountDeletionStatus(receipt.ticket), receipt.ticket); }
    catch (reason) {
      setUncertain(true);
      setError(reason instanceof Error ? reason.message : "暂时无法查询注销结果。");
    } finally { setBusy(false); }
  }, [applyStatus, receipt]);

  useEffect(() => {
    if (status?.status !== "processing" || !receipt || busy || uncertain) return;
    const timer = window.setTimeout(() => { void checkStatus(); }, 5_000);
    return () => window.clearTimeout(timer);
  }, [status, receipt, busy, uncertain, checkStatus]);

  async function verify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!eligibility?.eligible || !acknowledged || busy) return;
    setBusy(true); setError("");
    try { setVerification(await verifyAccountDeletion(password)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "身份验证未完成。"); }
    finally { setPassword(""); setBusy(false); }
  }

  async function confirmDeletion() {
    if (!verification || !acknowledged || busy) return;
    if (Date.parse(verification.expires_at) <= Date.now()) {
      setVerification(null); setAcknowledged(false);
      setError(en ? "Verification expired. Verify your password again." : "验证已过期，请重新验证密码。");
      return;
    }
    const saved = newDeletionReceipt(verification);
    try { saveDeletionReceipt(window.localStorage, saved); }
    catch {
      setError(en ? "Allow site storage before submitting so the result can be recovered after a timeout." : "请先允许本站保存注销查询凭据，以便网络中断后确认结果；本次尚未提交。");
      return;
    }
    setReceipt(saved); setVerification(null); setBusy(true); setError("");
    await sendConfirmedReceipt(saved);
  }

  async function sendConfirmedReceipt(saved: DeletionReceipt) {
    if (saved.verifyExpiresAt && saved.verifyExpiresAt <= Date.now()) {
      setRetryConfirmation(false); setBusy(false);
      setError(en ? "The verification window has expired. Keep checking the result; an expired receipt cannot start deletion." : "身份验证时限已过，过期验证不能启动注销。请保留凭据查询结果，确认尚未开始后可重新验证。");
      return;
    }
    setBusy(true); setError(""); setRetryConfirmation(false);
    try { applyStatus(await submitDeletionWithRecovery(saved.ticket, submitAccountDeletion, getAccountDeletionStatus), saved.ticket); }
    catch (reason) {
      setUncertain(true);
      setError(reason instanceof Error ? reason.message : "暂时无法查询注销结果。");
    } finally { setBusy(false); }
  }

  function recheckEligibility() {
    // A verified result after timeout keeps its original receipt for explicit
    // retry/recovery. Only a blocked result can start a fresh eligibility check.
    if (receipt && status?.status !== "blocked") return;
    try { if (receipt) clearDeletionReceipt(window.localStorage, receipt.ticket); } catch { /* A future visit can safely query the old receipt. */ }
    setReceipt(null); setStatus(null); setVerification(null); setAcknowledged(false); setUncertain(false);
    void loadEligibility();
  }

  async function restartExpiredVerification() {
    if (!receipt?.verifyExpiresAt || receipt.verifyExpiresAt > Date.now() || busy) return;
    setBusy(true); setError("");
    try {
      // Re-check the old receipt before allowing the user to explicitly replace
      // it. A request which started in the meantime must never be lost.
      const latest = await getAccountDeletionStatus(receipt.ticket);
      applyStatus(latest, receipt.ticket);
      if (latest.status === "verified" || latest.status === "blocked") {
        clearDeletionReceipt(window.localStorage, receipt.ticket);
        setReceipt(null); setStatus(null); setAcknowledged(false);
        await loadEligibility();
      }
    } catch (reason) {
      setUncertain(true);
      setError(reason instanceof Error ? reason.message : "暂时无法确认原申请状态。");
    } finally { setBusy(false); }
  }

  const complete = status?.status === "completed";
  const started = deletionRevokesNormalSession(status);
  const blockers = status?.status === "blocked" || status?.status === "processing" ? status.blockers : eligibility?.blockers || [];
  const verificationExpired = Boolean(receipt?.verifyExpiresAt && receipt.verifyExpiresAt <= Date.now());

  return <div className="site-page public-v2 information-page">
    <SiteHeader authMode={started || Boolean(receipt) ? "guest" : "auto"} />
    <main className={`public-data-page ${styles.page}`}>
      <header className={styles.heading}>
        <p className="hero-eyebrow">WOD / ACCOUNT</p>
        <h1>{en ? "Delete your WOD account" : "注销 WOD 账号"}</h1>
        <p>{en ? "You can request account deletion here, even if you have uninstalled the app." : "即使已经卸载 App，也可以在此申请注销账号，无需重新安装。"}</p>
      </header>
      <section className={styles.card} aria-labelledby="deletion-notice-title">
        <h2 id="deletion-notice-title">{en ? "Before you continue" : "注销前，请了解"}</h2>
        <ul className={styles.noticeList}>
          <li>{en ? "This deletes your WOD account, not just signs you out. Once completed, this WOD account cannot be restored." : "注销不是退出登录。注销完成后，此 WOD 账号无法恢复。"}</li>
          <li>{en ? "All WOD sessions and its linked Kai sign-in will be disabled. This does not delete your external Kai account." : "所有 WOD 登录会话将失效，Kai 登录关联将解除；这不会注销外部 Kai 统一身份账号。"}</li>
          <li>{en ? "Personal profile data and other deletable data will be cleared. Records required for outstanding obligations, disputes, audit or legal duties are retained only as necessary with restricted access." : "个人资料及可删除数据会被清理；履约、争议、审计或法定义务确需保留的记录，仅在必要范围内受限保存。"}</li>
          <li>{en ? "The server checks ongoing cooperation, active resources, balances and unsettled rewards. Deletion does not waive money or rewards owed to you." : "系统会检查未结束合作、使用中资源、余额及待结算返佣；不会以注销为由擅自清零资金或取消既有返佣。"}</li>
        </ul>
        <p className={styles.note}>{en ? "Read the " : "请阅读"}<Link href="/privacy">{en ? "privacy notice" : "隐私说明"}</Link>{en ? " for the account-data notice." : "中的账号数据处理说明。"}</p>
      </section>

      <section className={styles.card} aria-labelledby="deletion-action-title" aria-busy={busy}>
        <h2 id="deletion-action-title">{complete ? (en ? "Account deleted" : "账号已注销") : en ? "Request deletion" : "申请注销"}</h2>
        {error && <p className="commerce-error" role="alert">{error}</p>}
        {complete ? <div role="status">
          <p>{en ? "The server confirmed that your WOD account has been deleted. Its normal sign-in sessions are no longer valid." : "服务器已确认此 WOD 账号注销完成，原有登录会话已失效。"}</p>
          {status.completed_at && <p className={styles.note}>{en ? "Completed at: " : "完成时间："}{new Date(status.completed_at).toLocaleString(en ? "en-US" : "zh-CN")}</p>}
          <a className="outline-link" href="/">{en ? "Back to home" : "返回首页"}</a>
        </div> : receipt ? <div aria-live="polite">
          <p className={styles.note}>{en ? "This receipt belongs to the previously confirmed deletion request. Switching the browser's signed-in account does not change the account being processed." : "此处查询的是此前已确认的注销申请；切换浏览器登录账号，不会改变原申请对应的账号。"}</p>
          <p>{uncertain
            ? (en ? "The result is not yet confirmed. Do not submit again. Your deletion-only receipt is saved on this browser so you can keep checking." : "目前尚未确认注销结果，请勿重复提交。本浏览器已保留专用查询凭据，可以继续查询。")
            : status?.status === "processing"
              ? blockers.length
                ? (en ? "Normal sign-in is disabled, but these outstanding items are delaying data cleanup. Account deletion is not yet complete." : "正常登录已停用，但以下未处理事项阻止了资料清理，注销尚未完成。")
                : (en ? "Deletion is being processed. Normal sign-in is disabled. Completion will only be shown when confirmed by the server." : "注销正在处理中，正常登录已停用。只有服务器确认完成后，才会显示注销成功。")
              : status?.status === "blocked"
                ? (en ? "Deletion has not started. Resolve the items below, then check eligibility again." : "注销尚未开始。请先处理以下事项，再重新检查注销条件。")
                : status?.status === "verified"
                  ? (en ? "The server currently confirms identity verification only; deletion has not started. Keep this receipt to check again or explicitly retry with the same verification." : "服务器当前仅记录了身份验证，注销尚未开始。请保留原查询凭据继续核实，或明确确认后使用原验证重试。")
                  : (en ? "Checking the deletion result…" : "正在查询注销结果…")}</p>
          {blockers.length > 0 && <ul className={styles.blockers}>{blockers.map((item) => <li key={item.code}>{item.message}{item.count > 1 ? ` (${item.count})` : ""}</li>)}</ul>}
          <div className={styles.actions}>
            <button type="button" className="outline-link" disabled={busy} onClick={() => void checkStatus()}>{busy ? (en ? "Checking…" : "查询中…") : en ? "Check result" : "查询注销结果"}</button>
            {!uncertain && status?.status === "blocked" && <button type="button" className="outline-link" disabled={busy} onClick={recheckEligibility}>{en ? "Check requirements again" : "重新检查条件"}</button>}
            {!uncertain && status?.status === "verified" && !verificationExpired && <button type="button" className="outline-link" disabled={busy} onClick={() => setRetryConfirmation(true)}>{en ? "Review and retry with this receipt" : "使用原验证再次确认"}</button>}
            {!uncertain && status?.status === "verified" && verificationExpired && <button type="button" className="outline-link" disabled={busy} onClick={() => void restartExpiredVerification()}>{en ? "Recheck result and verify identity again" : "核实原结果并重新验证身份"}</button>}
          </div>
          {retryConfirmation && status?.status === "verified" && <section className={styles.confirmation} aria-labelledby="deletion-retry-title">
            <h3 id="deletion-retry-title">{en ? "Confirm retry" : "确认再次提交"}</h3>
            <p>{en ? "This uses the same deletion-only verification, not a new request. Deletion is irreversible once completed." : "此次将使用原来的注销验证，不创建另一份申请。注销完成后无法恢复。"}</p>
            <div className={styles.actions}><button type="button" className="outline-link" disabled={busy} onClick={() => setRetryConfirmation(false)}>{en ? "Cancel" : "取消"}</button><button type="button" className={styles.dangerButton} disabled={busy} onClick={() => void sendConfirmedReceipt(receipt)}>{en ? "Confirm retry of account deletion" : "确认重试注销"}</button></div>
          </section>}
          <p className={styles.note}>{en ? "Only the deletion-specific receipt is saved, for up to 7 days. No password or normal sign-in token is stored. If this browser's storage is cleared, result recovery may require support." : "仅保存最长 7 天的注销专用查询凭据，不保存密码或普通登录令牌。清理浏览器数据后，可能需要通过客服核实结果。"}</p>
        </div> : guest ? <div>
          <p>{en ? "Sign in to the WOD account you want to delete, then verify your WOD password on this page." : "请先登录要注销的 WOD 账号，再在此页面验证 WOD 登录密码。"}</p>
          <Link className="commerce-primary" href={loginHref("/account-deletion")}>{en ? "Sign in to continue" : "登录后继续注销"}</Link>
        </div> : verification ? <section className={styles.confirmation} aria-labelledby="deletion-final-title">
          <h3 id="deletion-final-title">{en ? "Final confirmation" : "最后确认"}</h3>
          <p>{en ? "Identity verified. Clicking the button below submits an irreversible request to delete this WOD account. The server will check outstanding items again." : "身份已验证。点击下方按钮将正式申请注销此 WOD 账号，完成后不可恢复。服务器仍会再次检查是否有未处理事项。"}</p>
          <div className={styles.actions}>
            <button type="button" className="outline-link" disabled={busy} onClick={() => { setVerification(null); setAcknowledged(false); }}>{en ? "Go back" : "返回"}</button>
            <button type="button" className={styles.dangerButton} disabled={busy || !acknowledged} onClick={() => void confirmDeletion()}>{en ? "Confirm account deletion" : "确认注销账号"}</button>
          </div>
        </section> : eligibility ? <>
          <p role="status">{eligibility.eligible ? (en ? "The server found no blocking items. Verify your identity below to continue." : "服务器检查通过，没有阻止注销的事项。请继续验证身份。") : en ? "Resolve these items before requesting deletion:" : "请先处理以下事项，再申请注销："}</p>
          {blockers.length > 0 && <ul className={styles.blockers}>{blockers.map((item) => <li key={item.code}>{item.message}{item.count > 1 ? ` (${item.count})` : ""}</li>)}</ul>}
          {eligibility.automatic_actions.length > 0 && <div className={styles.note}><strong>{en ? "Included in the deletion process" : "确认注销后将一并处理"}</strong><ul>{eligibility.automatic_actions.map((action) => <li key={action}>{action}</li>)}</ul></div>}
          {eligibility.eligible && <form className={styles.form} onSubmit={verify}>
            <label htmlFor="deletion-password">{en ? "WOD sign-in password" : "WOD 登录密码"}</label>
            <input id="deletion-password" type="password" required autoComplete="current-password" maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} disabled={busy}/>
            <p className={styles.note}>{en ? "Enter your WOD password, not your external Kai password. SMS verification is not available in this version." : "请填写 WOD 密码，不是外部 Kai 统一身份密码。本版不提供短信验证。"}</p>
            <label className={styles.acknowledgment}><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} disabled={busy}/><span>{en ? "I have read the notice and understand that this WOD account cannot be restored after deletion." : "我已阅读注销说明，理解此 WOD 账号注销完成后无法恢复。"}</span></label>
            <button className={styles.dangerButton} type="submit" disabled={busy || !acknowledged || !password}>{busy ? (en ? "Verifying…" : "验证中…") : en ? "Verify identity and continue" : "验证身份并继续"}</button>
          </form>}
          {!eligibility.eligible && <button className="outline-link" disabled={busy} type="button" onClick={() => void loadEligibility()}>{en ? "Check again" : "重新检查"}</button>}
        </> : busy ? <p role="status">{en ? "Checking account eligibility…" : "正在检查账号注销条件…"}</p> : <button type="button" className="outline-link" onClick={() => void loadEligibility()}>{en ? "Try again" : "重新检查"}</button>}
        <p className={styles.note}><a href="tel:+864001082026">+86 4001082026</a></p>
      </section>
    </main>
    <SiteFooter />
  </div>;
}
