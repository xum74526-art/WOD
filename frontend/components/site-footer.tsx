import Link from "next/link";
import { Brand } from "@/components/brand";

export function SiteFooter() {
  return (
    <footer className="site-footer site-footer--kai">
      <div className="site-footer__brand">
        <Brand />
        <p>KAI 未来算力中心。连接机构需求、容量供应商与可核对的算力交付。</p>
        <small>© 2026 KAI. 服务及参数以正式服务文件及生效版本为准。</small>
      </div>
      <nav aria-label="产品"><strong>产品</strong><Link href="/market">服务器市场</Link><Link href="/market/trends">算力行情</Link><Link href="/account/leases">我的服务器</Link></nav>
      <nav aria-label="生态"><strong>生态</strong><Link href="/community">算力社区</Link><Link href="/requests">公开求购</Link><Link href="/supplier/apply">商家入驻</Link></nav>
      <nav aria-label="公司"><strong>公司</strong><Link href="/about">关于 KAI</Link><Link href="/contact">联系我们</Link><a href="mailto:access@kai.com">access@kai.com</a></nav>
      <nav aria-label="支持"><strong>支持</strong><Link href="/help">帮助中心</Link><Link href="/terms">用户协议</Link><Link href="/privacy">隐私说明</Link></nav>
    </footer>
  );
}
