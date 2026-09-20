"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowLeft } from "@phosphor-icons/react";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { useI18n } from "@/components/locale-root";
import { toTraditionalChinese } from "@/lib/traditional-chinese";

type SimplePageProps = {
  title: string;
  description: string;
  titleEn?: string;
  descriptionEn?: string;
  body?: string;
  bodyEn?: string;
  children?: ReactNode;
};

export function SimplePage({ title, description, titleEn, descriptionEn, body, bodyEn, children }: SimplePageProps) {
  const { locale } = useI18n();
  const localize = (simplified: string, english?: string) => {
    if (locale === "en") return english || simplified;
    return locale === "zh-Hant" ? toTraditionalChinese(simplified) : simplified;
  };
  const hasBody = body !== undefined || bodyEn !== undefined;
  const fallbackBody = localize(
    "此页面将在对应业务服务接入时补充正式内容，目前不会显示虚构条款或状态。",
    "Formal content will be added when the corresponding service is ready. This page does not display invented terms or status.",
  );
  return (
    <div className="site-page public-v2 information-page">
      <SiteHeader />
      <main className="public-data-page kai-simple-page">
        <header><p className="hero-eyebrow">KAI星算 / INFORMATION</p><h1>{localize(title, titleEn)}</h1><p>{localize(description, descriptionEn)}</p></header>
        <section>{hasBody ? <p>{localize(body || "", bodyEn)}</p> : children ? null : <p>{fallbackBody}</p>}{children}<Link className="outline-link" href="/"><ArrowLeft size={16}/>{localize("返回首页", "Back to home")}</Link></section>
      </main>
      <SiteFooter />
    </div>
  );
}
