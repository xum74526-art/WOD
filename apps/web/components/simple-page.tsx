"use client";

import Link from "next/link";
import { ArrowLeft } from "@phosphor-icons/react";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { useI18n } from "@/components/locale-root";

type SimplePageProps = {
  title: string;
  description: string;
  titleEn?: string;
  descriptionEn?: string;
};

export function SimplePage({ title, description, titleEn, descriptionEn }: SimplePageProps) {
  const { locale } = useI18n();
  return (
    <div className="site-page">
      <SiteHeader />
      <main className="public-data-page kai-simple-page">
        <header><p className="hero-eyebrow">KAI / INFORMATION</p><h1>{locale === "en" ? titleEn || title : title}</h1><p>{locale === "en" ? descriptionEn || description : description}</p></header>
        <section><p>{locale === "en" ? "Formal content will be added when the corresponding service is ready. This page does not display invented terms or status." : "此页面将在对应业务服务接入时补充正式内容，目前不会显示虚构条款或状态。"}</p><Link className="outline-link" href="/"><ArrowLeft size={16}/>{locale === "en" ? "Back to home" : "返回首页"}</Link></section>
      </main>
      <SiteFooter />
    </div>
  );
}
