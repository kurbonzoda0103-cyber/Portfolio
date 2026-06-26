import { NextRequest, NextResponse } from "next/server";

const YT = "https://www.googleapis.com/youtube/v3";

const NICHE_RPM: Record<string, number> = {
  finance: 15, business: 12, health: 10, technology: 8,
  education: 6, travel: 5, food: 4, gaming: 2, entertainment: 3,
};

function estimateRpm(query: string): number {
  const q = query.toLowerCase();
  for (const [key, rpm] of Object.entries(NICHE_RPM)) {
    if (q.includes(key)) return rpm;
  }
  return 3;
}

function estimateMonthlyRevenue(totalViews: number, publishedAt: string, rpm: number): number {
  const months = Math.max(1, (Date.now() - new Date(publishedAt).getTime()) / (1000 * 60 * 60 * 24 * 30));
  const monthlyViews = totalViews / months;
  return Math.round((monthlyViews / 1000) * rpm);
}

function outlierScore(subscribers: number, totalViews: number, videoCount: number): number {
  if (!subscribers || !videoCount) return 0;
  const avgViewsPerVideo = totalViews / videoCount;
  const ratio = avgViewsPerVideo / (subscribers * 0.1);
  return Math.min(Math.round(ratio * 10) / 10, 5);
}

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q");
  if (!q) return NextResponse.json({ error: "Query required" }, { status: 400 });

  const key = process.env.YOUTUBE_API_KEY;
  if (!key) return NextResponse.json({ error: "YOUTUBE_API_KEY не задан в .env.local" }, { status: 500 });

  try {
    const searchRes = await fetch(
      `${YT}/search?part=snippet&type=channel&q=${encodeURIComponent(q)}&maxResults=12&key=${key}`
    );
    if (!searchRes.ok) throw new Error(`YouTube API ${searchRes.status}`);
    const search = await searchRes.json();

    const ids = search.items?.map((i: { id: { channelId: string } }) => i.id.channelId).join(",");
    if (!ids) return NextResponse.json({ query: q, channels: [], avgRpm: 0, totalChannels: 0 });

    const statsRes = await fetch(
      `${YT}/channels?part=snippet,statistics&id=${ids}&key=${key}`
    );
    if (!statsRes.ok) throw new Error(`YouTube API ${statsRes.status}`);
    const stats = await statsRes.json();

    const rpm = estimateRpm(q);

    const channels = (stats.items || []).map((ch: {
      id: string;
      snippet: { title: string; description: string; publishedAt: string; thumbnails?: { medium?: { url: string } } };
      statistics: { subscriberCount?: string; viewCount?: string; videoCount?: string };
    }) => {
      const subs = parseInt(ch.statistics.subscriberCount || "0");
      const views = parseInt(ch.statistics.viewCount || "0");
      const videos = parseInt(ch.statistics.videoCount || "0");
      return {
        id: ch.id,
        title: ch.snippet.title,
        niche: q,
        subscribers: subs,
        views,
        estimatedMonthlyRevenue: estimateMonthlyRevenue(views, ch.snippet.publishedAt, rpm),
        thumbnailUrl: ch.snippet.thumbnails?.medium?.url || null,
        outlierScore: outlierScore(subs, views, videos),
        uploadsPerMonth: null,
        qualityRating: subs > 100_000 ? "high" : subs > 10_000 ? "mid" : "low",
        isFaceless: false,
      };
    });

    return NextResponse.json({ query: q, channels, avgRpm: rpm, totalChannels: channels.length });
  } catch (err: unknown) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "Error" }, { status: 500 });
  }
}
