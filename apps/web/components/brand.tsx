"use client";

import Image from "next/image";
import Link from "next/link";
import { useI18n } from "@/components/locale-root";

type BrandProps = {
  inverse?: boolean;
};

export function Brand({ inverse = false }: BrandProps) {
  const { locale } = useI18n();
  return (
    <Link className={`brand${inverse ? " brand--inverse" : ""}`} href="/" aria-label={locale === "en" ? "北斗 kai home" : "北斗 kai 首页"}>
      <Image className="brand__logo" src="/kai-logo.svg" alt="" width={72} height={32} priority />
      <span className="brand__name">北斗 <b>kai</b></span>
    </Link>
  );
}
