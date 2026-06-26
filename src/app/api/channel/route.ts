import { NextRequest, NextResponse } from "next/server";

const YT = "https://www.googleapis.com/youtube/v3";

function extractChannelId(url: string): { type: "id" | "handle" | "username"; value: string } {
  try {
    const u = new URL(url);
    const path = u.pathname;
    if (path.startsWith("/@")) return { type: "handle", value: path.slice(2) };
    if (path.startsWith("/channel/")) return { type: "id", value: path.split("/channel/")[1].split("/")[0] };
    if (path.startsWith("/user/")) return { type: "username", value: path.split("/user/")[1].split("/")[0] };
  } catch { /* bare value */ }
  if (url.startsWith("@")) return { type: "handle", value: url.slice(1) };
  if (url.startsWith("UC")) return { type: "id", value: url };
  return { type: "handle", value: url };
}

const NICHE_RPM: Record<string, number> = {
  finance: 15, business: 12, health: 10, technology: 8, education: 6, default: 3,
};

function guessCategoryRpm(desc: string): number {
  const d = desc.toLowerCase();
  for (const [key, rpm] of Object.entries(NICHE_RPM)) {
    if (d.includes(key)) return rpm;
  }
  return NICHE_RPM.default;
}

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url");
  if (!url) return NextResponse.json({ error: "url required" }, { status: 400 });

  const key = process.env.YOUTUBE_API_KEY;
  if (!key) return NextResponse.json({ error: "YOUTUBE_API_KEY не задан" }, { status: 500 });

  try {
    const ref = extractChannelId(url);
    const paramKey = ref.type === "id" ? "id" : ref.type === "handle" ? "forHandle" : "forUsername";

    const chRes = await fetch(
      `${YT}/channels?part=snippet,statistics&${paramKey}=${encodeURIComponent(ref.value)}&key=${key}`
    );
    if (!chRes.ok) throw new Error(`YouTube API ${chRes.status}`);
    const chData = await chRes.json();

    const ch = chData.items?.[0];
    if (!ch) return NextResponse.json({ error: "Канал не найден" }, { status: 404 });

    const subs = parseInt(ch.statistics.subscriberCount || "0");
    const totalViews = parseInt(ch.statistics.viewCount || "0");
    const videoCount = parseInt(ch.statistics.videoCount || "0");
    const months = Math.max(1, (Date.now() - new Date(ch.snippet.publishedAt).getTime()) / (1000 * 60 * 60 * 24 * 30));
    const rpm = guessCategoryRpm(ch.snippet.description || "");
    const monthlyViews = totalViews / months;
    const monthlyRevenue = Math.round((monthlyViews / 1000) * rpm);

    const topRes = await fetch(
      `${YT}/search?part=snippet&channelId=${ch.id}&order=viewCount&type=video&maxResults=5&key=${key}`
    );
    const topData = topRes.ok ? await topRes.json() : { items: [] };

    let topVideos: { id: string; title: string; views: number; publishedAt: string }[] = [];
    if (topData.items?.length) {
      const vids = topData.items.map((i: { id: { videoId: string } }) => i.id.videoId).join(",");
      const vRes = await fetch(`${YT}/videos?part=statistics,snippet&id=${vids}&key=${key}`);
      if (vRes.ok) {
        const vData = await vRes.json();
        topVideos = (vData.items || []).map((v: {
          id: string;
          snippet: { title: string; publishedAt: string };
          statistics: { viewCount?: string };
        }) => ({
          id: v.id,
          title: v.snippet.title,
          views: parseInt(v.statistics.viewCount || "0"),
          publishedAt: v.snippet.publishedAt,
        }));
      }
    }

    return NextResponse.json({
      id: ch.id,
      title: ch.snippet.title,
      description: ch.snippet.description || "",
      subscribers: subs,
      totalViews,
      videoCount,
      monthlyRevenue,
      avgViewsPerVideo: videoCount ? Math.round(totalViews / videoCount) : 0,
      uploadsPerMonth: Math.round(videoCount / months),
      subscriberGrowthRate: 0,
      estimatedYearlyRevenue: monthlyRevenue * 12,
      topVideos,
      recentGrowth: 0,
      isFaceless: false,
      niche: "",
      rpm,
    });
  } catch (err: unknown) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "Error" }, { status: 500 });
  }
}
