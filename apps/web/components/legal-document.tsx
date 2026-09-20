"use client";

import Link from "next/link";
import { useI18n } from "@/components/locale-root";
import {
  LEGAL_EFFECTIVE_DATE,
  LEGAL_ICP_FILING,
  LEGAL_OPERATOR,
  LEGAL_OPERATOR_ADDRESS,
  LEGAL_VERSION,
  toTraditionalLegalText,
} from "@/lib/legal-text";

export type LegalText = {
  zh: string;
  en: string;
  sensitive?: boolean;
};

export type LegalSection = {
  id: string;
  title: LegalText;
  paragraphs?: LegalText[];
  items?: LegalText[];
};

type LegalDocumentProps = {
  sections: LegalSection[];
  accountDeletionLink?: boolean;
  localeOverride?: "zh-Hans" | "zh-Hant" | "en";
};

export function LegalDocument({ sections, accountDeletionLink = false, localeOverride }: LegalDocumentProps) {
  const { locale: selectedLocale } = useI18n();
  const locale = localeOverride || selectedLocale;
  const text = (copy: LegalText) => {
    if (locale === "en") return copy.en;
    return locale === "zh-Hant" ? toTraditionalLegalText(copy.zh) : copy.zh;
  };
  const localize = (zh: string, en: string) => text({ zh, en });

  return (
    <article className="legal-document">
      <dl className="legal-document__meta">
        <div><dt>{localize("版本", "Version")}</dt><dd>{LEGAL_VERSION}</dd></div>
        <div><dt>{localize("更新日期", "Last updated")}</dt><dd>{LEGAL_EFFECTIVE_DATE}</dd></div>
        <div><dt>{localize("生效日期", "Effective date")}</dt><dd>{LEGAL_EFFECTIVE_DATE}</dd></div>
        <div><dt>{localize("运营主体", "Operator")}</dt><dd>{localize(LEGAL_OPERATOR, "Zircon Core Futures Computing Artificial Intelligence Technology (Shanghai) Co., Ltd.")}</dd></div>
      </dl>

      <div className="legal-document__sections">
        {sections.map((section, index) => (
          <section id={section.id} key={section.id}>
            <h2><span>{String(index + 1).padStart(2, "0")}</span>{text(section.title)}</h2>
            {section.paragraphs?.map((paragraph, paragraphIndex) => <p className={paragraph.sensitive ? "legal-document__sensitive" : undefined} key={`${section.id}-p-${paragraphIndex}`}>{text(paragraph)}</p>)}
            {section.items?.length ? <ul>{section.items.map((item, itemIndex) => <li className={item.sensitive ? "legal-document__sensitive" : undefined} key={`${section.id}-i-${itemIndex}`}>{text(item)}</li>)}</ul> : null}
          </section>
        ))}
      </div>

      <footer className="legal-document__contact">
        <div>
          <strong>{localize("个人信息保护与服务联系", "Privacy and service contact")}</strong>
          <p>{localize(`运营主体：${LEGAL_OPERATOR}`, `Operator: Zircon Core Futures Computing Artificial Intelligence Technology (Shanghai) Co., Ltd.`)}</p>
          <p>{localize(`联系地址：${LEGAL_OPERATOR_ADDRESS}`, `Address: ${LEGAL_OPERATOR_ADDRESS}`)}</p>
          <p>{localize(`网站 ICP 备案：${LEGAL_ICP_FILING}`, `Website ICP filing: ${LEGAL_ICP_FILING}`)}</p>
        </div>
        <a href="tel:+864001082026">{localize("联系我们：+86 4001082026", "Contact us: +86 4001082026")}</a>
        {accountDeletionLink ? <Link href="/account-deletion">{localize("申请注销KAI星算账号", "Request KAI星算 account deletion")}</Link> : null}
      </footer>
    </article>
  );
}
