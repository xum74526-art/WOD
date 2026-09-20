import type { Metadata } from "next";
import type { KaiLocale } from "./language.ts";

export type LocalizedMetadataCopy = Record<KaiLocale, {
  title: string;
  description: string;
}>;

export function buildLocalizedMetadata(
  locale: KaiLocale,
  copy: LocalizedMetadataCopy,
  shared: Metadata = {},
): Metadata {
  const selected = copy[locale];
  return {
    ...shared,
    title: { absolute: selected.title },
    description: selected.description,
  };
}
