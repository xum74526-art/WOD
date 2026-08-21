import type { Metadata } from "next";
import { AndroidLogo, AppleLogo, DownloadSimple, ShieldCheck, Storefront } from "@phosphor-icons/react/dist/ssr";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = {
  title: "下载 KAI App",
  description: "下载 KAI Android App，或查看 iOS 与 Android 应用商店发布状态。",
};

const androidApkUrl = process.env.NEXT_PUBLIC_KAI_ANDROID_APK_URL?.trim();

export default function DownloadPage() {
  return (
    <div className="site-page download-page">
      <SiteHeader />
      <main className="download-page__main">
        <header className="download-hero">
          <p className="hero-eyebrow">KAI MOBILE / 1.0.3</p>
          <h1>把算力市场<br />装进口袋</h1>
          <p>网页与 App 使用同一个 KAI 账号、余额、订单和算力数据。选择你的设备开始使用。</p>
        </header>

        <section className="download-platforms" aria-label="KAI App 下载方式">
          <article className="download-platform download-platform--android">
            <div className="download-platform__head">
              <span className="download-platform__icon"><AndroidLogo size={34} weight="fill" /></span>
              <div><small>ANDROID</small><h2>Android</h2></div>
              <span className="download-status">优先发布</span>
            </div>
            <p>适用于 Android 8.0 及以上设备。APK 发布后可直接下载安装，也可等待应用商店版本。</p>
            <div className="download-platform__actions">
              {androidApkUrl ? (
                <a className="download-primary" href={androidApkUrl} download>
                  <DownloadSimple size={19} weight="bold" />下载 APK
                </a>
              ) : (
                <span className="download-primary is-disabled" aria-disabled="true">
                  <DownloadSimple size={19} />APK 正在准备
                </span>
              )}
              <a className="download-store-placeholder" href="/download#android-store" aria-disabled="true" tabIndex={-1}>
                <Storefront size={18} />Android 应用商店<span>即将上线</span>
              </a>
            </div>
            <dl className="download-build-info">
              <div><dt>版本</dt><dd>1.0.3</dd></div>
              <div><dt>格式</dt><dd>APK</dd></div>
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
              <div><dt>版本</dt><dd>1.0.3</dd></div>
              <div><dt>系统</dt><dd>iOS 13+</dd></div>
              <div><dt>渠道</dt><dd>App Store</dd></div>
            </dl>
          </article>
        </section>

        <aside className="download-security-note">
          <ShieldCheck size={21} weight="duotone" />
          <div><strong>只从 KAI 官方页面安装</strong><span>正式 APK 发布时，这里会显示文件大小和校验信息。应用商店入口在审核通过前保持占位状态。</span></div>
        </aside>
      </main>
      <SiteFooter />
    </div>
  );
}
