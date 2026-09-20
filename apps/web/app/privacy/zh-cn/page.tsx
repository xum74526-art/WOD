import type { Metadata } from "next";
import { LegalDocument } from "@/components/legal-document";
import { privacySections } from "../page";

export const metadata: Metadata = {
  title: "算力星图隐私政策",
  description: "算力星图面向中国大陆应用商店审核与用户查阅的简体中文隐私政策。",
  robots: { index: true, follow: false },
};

export default function SimplifiedChinesePrivacyPage() {
  return (
    <main className="privacy-review-page">
      <header>
        <p>算力星图 / 隐私政策</p>
        <h1>隐私政策</h1>
      </header>
      <LegalDocument sections={privacySections} localeOverride="zh-Hans" />
    </main>
  );
}
