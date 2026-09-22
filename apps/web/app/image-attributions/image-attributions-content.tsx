"use client";

import Link from "next/link";
import { ArrowLeft, ArrowSquareOut } from "@phosphor-icons/react";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { useI18n } from "@/components/locale-root";
import { toTraditionalChinese } from "@/lib/traditional-chinese";
import styles from "./page.module.css";

type LocalizedText = { zh: string; en: string };
type Attribution = {
  asset: string;
  work: string;
  author: string;
  sourceUrl: string;
  license: string;
  licenseUrl: string;
  modification: LocalizedText;
  aliases: string[];
};

const attributions: Attribution[] = [
  {
    asset: "RTX2060.jpg",
    work: "NVIDIA GeForce RTX 2060",
    author: "Mr ATM",
    sourceUrl: "https://commons.wikimedia.org/wiki/File:NVIDIA_GeForce_RTX_2060.jpg",
    license: "CC BY 2.0",
    licenseUrl: "https://creativecommons.org/licenses/by/2.0/",
    modification: { zh: "居中裁剪为 16:9、缩放并进行 JPEG 压缩。", en: "Center-cropped to 16:9, resized and JPEG-compressed." },
    aliases: ["RTX 2070", "RTX 2070 SUPER"],
  },
  {
    asset: "RTX3070.jpg",
    work: "MSI GeForce RTX 3070 VENTUS 3X OC",
    author: "TheStriker",
    sourceUrl: "https://commons.wikimedia.org/wiki/File:MSI_GeForce_RTX_3070_VENTUS_3X_OC.jpg",
    license: "CC BY 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by/4.0/",
    modification: { zh: "居中裁剪为 16:9、缩放并进行 JPEG 压缩。", en: "Center-cropped to 16:9, resized and JPEG-compressed." },
    aliases: ["RTX 3050", "RTX 3060", "RTX 3060 Ti", "RTX 3070 Ti"],
  },
  {
    asset: "RTX4070.jpg",
    work: "2023 Gigabyte GeForce RTX 4070 Aero OC 12GB (4)",
    author: "Jacek Halicki",
    sourceUrl: "https://commons.wikimedia.org/wiki/File:2023_Gigabyte_GeForce_RTX_4070_Aero_OC_12GB_(4).jpg",
    license: "CC BY-SA 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0/",
    modification: { zh: "居中裁剪为 16:9、缩放并进行 JPEG 压缩；衍生图片继续采用 CC BY-SA 4.0。", en: "Center-cropped to 16:9, resized and JPEG-compressed; the derivative remains under CC BY-SA 4.0." },
    aliases: ["RTX 4060", "RTX 4060 Ti", "RTX 4070 SUPER", "RTX 4070 Ti"],
  },
  {
    asset: "RTX5060Ti.jpg",
    work: "Nvidia GeForce RTX 5060 Ti 16GB, PNY Overclocked Dual Fan, front",
    author: "FreeMediaKid!",
    sourceUrl: "https://commons.wikimedia.org/wiki/File:Nvidia_GeForce_RTX_5060_Ti_16GB,_PNY_Overclocked_Dual_Fan,_front.jpg",
    license: "CC BY-SA 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by-sa/4.0/",
    modification: { zh: "居中裁剪为 16:9、缩放并进行 JPEG 压缩；衍生图片继续采用 CC BY-SA 4.0。", en: "Center-cropped to 16:9, resized and JPEG-compressed; the derivative remains under CC BY-SA 4.0." },
    aliases: ["RTX 5060"],
  },
  {
    asset: "RTX5070.jpg",
    work: "20260521 ASUS RTX 5070 graphics card",
    author: "Striker9498",
    sourceUrl: "https://commons.wikimedia.org/wiki/File:20260521_%EC%95%84%EC%88%98%EC%8A%A4_RTX5070_%EA%B7%B8%EB%9E%98%ED%94%BD%EC%B9%B4%EB%93%9C.jpg",
    license: "CC0 1.0",
    licenseUrl: "https://creativecommons.org/publicdomain/zero/1.0/",
    modification: { zh: "居中裁剪为 16:9、缩放并进行 JPEG 压缩。", en: "Center-cropped to 16:9, resized and JPEG-compressed." },
    aliases: ["RTX 5070 Ti"],
  },
  {
    asset: "RTX5080.jpg",
    work: "RTX 5080",
    author: "XD7006",
    sourceUrl: "https://commons.wikimedia.org/wiki/File:RTX_5080.png",
    license: "CC BY 4.0",
    licenseUrl: "https://creativecommons.org/licenses/by/4.0/",
    modification: { zh: "居中裁剪为 16:9，并转换为 JPEG。", en: "Center-cropped to 16:9 and converted to JPEG." },
    aliases: [],
  },
];

export function ImageAttributionsContent() {
  const { locale } = useI18n();
  const localize = (text: LocalizedText) => locale === "en" ? text.en : locale === "zh-Hant" ? toTraditionalChinese(text.zh) : text.zh;
  const label = (zh: string, en: string) => localize({ zh, en });

  return (
    <div className="site-page public-v2 information-page">
      <SiteHeader />
      <main className={`public-data-page ${styles.page}`}>
        <header>
          <p className="hero-eyebrow">IMAGE SOURCES / LICENSES</p>
          <h1>{label("图片来源与许可", "Image sources and licenses")}</h1>
          <p>{label(
            "以下 GPU 图片来自 Wikimedia Commons，并依照各原作标注的许可在KAI星算中使用。",
            "The following GPU images come from Wikimedia Commons and are used in KAI Star under the license identified for each original work.",
          )}</p>
          <p className={styles.notice}>{label(
            "商标和型号名称仅用于说明图片所示硬件，不代表相关品牌对KAI星算的认可或背书。",
            "Trademark and model names identify the depicted hardware only and do not imply endorsement of KAI Star by the relevant brands.",
          )}</p>
        </header>

        <section className={styles.grid} aria-label={label("Wikimedia Commons 图片署名", "Wikimedia Commons image attributions")}>
          {attributions.map((item) => (
            <article className={styles.card} key={item.asset}>
              <small>{item.asset}</small>
              <h2>{item.work}</h2>
              <dl>
                <div><dt>{label("作者", "Author")}</dt><dd>{item.author}</dd></div>
                <div><dt>{label("许可", "License")}</dt><dd>{item.license}</dd></div>
                <div><dt>{label("修改", "Modification")}</dt><dd>{localize(item.modification)}</dd></div>
                <div><dt>{label("复用型号", "Reused for models")}</dt><dd>{item.aliases.length ? item.aliases.join(" · ") : label("无", "None")}</dd></div>
              </dl>
              <div className={styles.links}>
                <a href={item.sourceUrl} target="_blank" rel="noreferrer">{label("查看原作", "View original work")} <ArrowSquareOut size={15} /></a>
                <a href={item.licenseUrl} target="_blank" rel="noreferrer">{label("许可全文", "License terms")} <ArrowSquareOut size={15} /></a>
              </div>
            </article>
          ))}
        </section>

        <section className={styles.directRights}>
          <h2>{label("其他项目图片", "Other project images")}</h2>
          <p>{label(
            "此页面未单独列出的项目图片由KAI星算运营方持有所有权或已取得直接使用授权。",
            "Project images not individually listed on this page are owned by, or directly licensed for use to, the operator of KAI Star.",
          )}</p>
          <p>{label(
            "数据中心和专业型号可能复用同系列示意图；页面显示的型号文字是资源规格的准确信息。B100 当前复用 H200 数据中心系列示意图。",
            "Data-center and professional models may reuse an illustration from the same family. The model label shown in the interface is the authoritative resource specification. B100 currently reuses the H200 data-center family illustration.",
          )}</p>
        </section>

        <Link className={styles.back} href="/"><ArrowLeft size={16} />{label("返回首页", "Back to home")}</Link>
      </main>
      <SiteFooter />
    </div>
  );
}
