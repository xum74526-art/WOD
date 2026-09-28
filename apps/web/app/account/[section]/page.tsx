import { notFound } from "next/navigation";
import { MobileAccountServices, type MobileAccountSection } from "@/components/mobile-account-services";

const mobileSections = new Set<MobileAccountSection>(["revenue", "referrals", "coupons", "bank-accounts"]);

export default async function AccountSectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  if (mobileSections.has(section as MobileAccountSection)) return <MobileAccountServices section={section as MobileAccountSection} />;
  notFound();
}
