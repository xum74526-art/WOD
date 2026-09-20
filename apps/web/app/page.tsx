import { HomePageContent } from "@/components/home-page-content";
import { getInitialGpuTrend, getInitialMarketRanking, getInitialPublicProducts } from "@/lib/server/public-page-data";

export default async function HomePage() {
  const [initialRanking, initialProducts] = await Promise.all([
    getInitialMarketRanking(),
    getInitialPublicProducts(),
  ]);
  const initialTrend = await getInitialGpuTrend(initialRanking);
  return <HomePageContent initialRanking={initialRanking} initialProducts={initialProducts} initialTrend={initialTrend} />;
}
