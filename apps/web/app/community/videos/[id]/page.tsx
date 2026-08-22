import { SiteHeader } from "@/components/site-header";
import { CommunityVideo } from "@/components/community-video";

export default async function VideoPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <div className="site-page public-v2"><SiteHeader /><main className="video-detail-page"><CommunityVideo videoId={id} /></main></div>;
}
