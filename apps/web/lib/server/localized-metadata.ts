import type { Metadata } from "next";
import { cookies } from "next/headers";
import { normalizeStoredLocale } from "@/lib/language";
import {
  buildLocalizedMetadata,
  type LocalizedMetadataCopy,
} from "@/lib/localized-metadata";

export async function localizedPageMetadata(
  copy: LocalizedMetadataCopy,
  shared: Metadata = {},
): Promise<Metadata> {
  const cookieStore = await cookies();
  const locale = normalizeStoredLocale(cookieStore.get("kai.locale")?.value);
  return buildLocalizedMetadata(locale, copy, shared);
}
