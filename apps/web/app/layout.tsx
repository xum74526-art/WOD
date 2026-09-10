import type { Metadata } from "next";
import "@radix-ui/themes/styles.css";
import "@fontsource-variable/dm-sans";
import "@fontsource-variable/work-sans";
import "@fontsource-variable/noto-sans-sc";
import "@fontsource-variable/noto-sans-tc";
import "@fontsource/dm-mono";
import "@fontsource/dm-mono/500.css";
import { ThemeRoot } from "@/components/theme-root";
import { LocaleRoot, type KaiLocale } from "@/components/locale-root";
import { normalizeStoredLocale } from "@/lib/language";
import { cookies } from "next/headers";
import "./globals.css";
import "./kai-ui.css";

export const metadata: Metadata = {
  title: {
    default: "北斗 kai 算力市場",
    template: "%s | 北斗 kai",
  },
  description: "比較、購買和管理真實 GPU 算力資源。",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const storedLocale = (await cookies()).get("kai.locale")?.value;
  const locale: KaiLocale = normalizeStoredLocale(storedLocale);
  return (
    <html lang={locale} data-locale={locale} data-scroll-behavior="smooth" data-color-mode="light" data-radius="square" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: `(function(){try{var k='kai.color-mode.v1',v=localStorage.getItem(k),d=v==='dark'||v==='light'?v:(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'),r=document.documentElement;r.classList.toggle('dark',d==='dark');r.dataset.colorMode=d;r.dataset.radius='square';r.style.colorScheme=d}catch(e){}})();` }} />
      </head>
      <body>
        <LocaleRoot initialLocale={locale}><ThemeRoot>{children}</ThemeRoot></LocaleRoot>
      </body>
    </html>
  );
}
