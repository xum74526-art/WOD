import type { Metadata } from "next";
import { AndroidLogo, AppleLogo, DownloadSimple, ShieldCheck, Storefront } from "@phosphor-icons/react/dist/ssr";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = {
  title: "下載KAI星算 App",
  description: "下載KAI星算 Android App，或查看 iOS 與 Android 應用商店發佈狀態。",
};

const androidVersion = "1.2.3";
const configuredAndroidApkUrl = process.env.NEXT_PUBLIC_KAI_ANDROID_APK_URL?.trim() || "";
const configuredAndroidApkSize = process.env.NEXT_PUBLIC_KAI_ANDROID_APK_SIZE?.trim() || "";
const configuredAndroidApkSha256 = process.env.NEXT_PUBLIC_KAI_ANDROID_APK_SHA256?.trim().toUpperCase() || "";
const androidReleaseReady = /^(?:https:\/\/wod\.kai\.com)?\/download\/suanlixingtu\.apk$/.test(configuredAndroidApkUrl)
  && Boolean(configuredAndroidApkSize)
  && /^[A-F0-9]{64}$/.test(configuredAndroidApkSha256);
const androidApkUrl = androidReleaseReady ? configuredAndroidApkUrl : "";
const androidApkSize = androidReleaseReady ? configuredAndroidApkSize : "待重新打包";
const androidApkSha256 = androidReleaseReady ? configuredAndroidApkSha256 : "";

export default function DownloadPage() {
  return (
    <div className="site-page public-v2 download-page">
      <SiteHeader />
      <main className="download-page__main">
        <header className="download-hero">
          <p className="hero-eyebrow">KAI星算 ANDROID / {androidVersion}</p>
          <h1>把算力市场<br />装进口袋</h1>
          <p>网页与 App 使用同一个KAI星算账号、余额、订单和算力数据。选择你的设备开始使用。</p>
        </header>

        <section className="download-platforms" aria-label="KAI星算 App 下载方式">
          <article className="download-platform download-platform--android">
            <div className="download-platform__head">
              <span className="download-platform__icon"><AndroidLogo size={34} weight="fill" /></span>
              <div><small>ANDROID</small><h2>Android</h2></div>
              <span className={`download-status${androidReleaseReady ? "" : " download-status--pending"}`}>{androidReleaseReady ? "优先发布" : "正在准备"}</span>
            </div>
            <p>{androidReleaseReady ? "适用于 Android 8.0 及以上设备。可从本页直接下载安装，也可等待应用商店版本。" : "适用于 Android 8.0 及以上设备。新版签名包完成校验后，本页将开放官方下载。"}</p>
            <div className="download-platform__actions">
              {androidApkUrl ? <a className="download-primary" href={androidApkUrl} download>
                <DownloadSimple size={19} weight="bold" />下载 APK
              </a> : <span className="download-primary is-disabled" aria-disabled="true">
                <DownloadSimple size={19} weight="bold" />APK 正在准备
              </span>}
              <a className="download-store-placeholder" href="/download#android-store" aria-disabled="true" tabIndex={-1}>
                <Storefront size={18} />Android 应用商店<span>即将上线</span>
              </a>
            </div>
            <dl className="download-build-info">
              <div><dt>版本</dt><dd>{androidVersion}</dd></div>
              <div><dt>大小</dt><dd>{androidApkSize}</dd></div>
              <div><dt>架构</dt><dd>ARM64 / ARMv7</dd></div>
            </dl>
          </article>

          <article className="download-platform download-platform--ios">
            <div className="download-platform__head">
              <span className="download-platform__icon"><AppleLogo size={34} weight="fill" /></span>
              <div><small>IOS</small><h2>iPhone</h2></div>
              <span className="download-status download-status--pending">等待上架</span>
            </div>
            <p>iOS 版本与 Android 共用业务能力。完成 Apple 审核后，将通过 App Store 正式提供。</p>
            <div className="download-platform__actions">
              <a className="download-store-placeholder download-store-placeholder--large" href="/download#ios-app-store" aria-disabled="true" tabIndex={-1}>
                <AppleLogo size={20} weight="fill" />App Store<span>即将上线</span>
              </a>
            </div>
            <dl className="download-build-info">
              <div><dt>版本</dt><dd>待发布</dd></div>
              <div><dt>系统</dt><dd>iOS 13+</dd></div>
              <div><dt>渠道</dt><dd>App Store</dd></div>
            </dl>
          </article>
        </section>

        <aside className="download-security-note">
          <ShieldCheck size={21} weight="duotone" />
          <div>
            <strong>只从KAI星算官方页面安装</strong>
            <span>{androidReleaseReady ? `Android APK ${androidVersion} · ${androidApkSize}` : "新版 APK 尚未开放下载"}</span>
            {androidApkSha256 ? <code>SHA-256: {androidApkSha256}</code> : null}
          </div>
        </aside>
      </main>
      <SiteFooter />
    </div>
  );
}
