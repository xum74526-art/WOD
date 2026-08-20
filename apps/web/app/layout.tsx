import type { Metadata } from "next";
import "@radix-ui/themes/styles.css";
import "@fontsource-variable/dm-sans";
import "@fontsource-variable/work-sans";
import "@fontsource-variable/noto-sans-sc";
import "@fontsource/dm-mono";
import "@fontsource/dm-mono/500.css";
import { ThemeRoot } from "@/components/theme-root";
import "./globals.css";
import "./kai-ui.css";

export const metadata: Metadata = {
  title: {
    default: "KAI 算力市场",
    template: "%s | KAI",
  },
  description: "比较、购买和管理真实 GPU 算力资源。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" data-scroll-behavior="smooth" data-color-mode="light" data-radius="square" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: `(function(){try{var k='kai.color-mode.v1',v=localStorage.getItem(k),d=v==='dark'||v==='light'?v:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'),r=document.documentElement;r.classList.toggle('dark',d==='dark');r.dataset.colorMode=d;r.dataset.radius='square';r.style.colorScheme=d}catch(e){}})();` }} />
      </head>
      <body>
        <ThemeRoot>{children}</ThemeRoot>
      </body>
    </html>
  );
}
