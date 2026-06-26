import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url");
  if (!url) return NextResponse.json({ error: "url required" }, { status: 400 });

  const apiKey = process.env.NEXLEV_API_KEY;
  if (!apiKey) return NextResponse.json({ error: "NEXLEV_API_KEY не задан" }, { status: 500 });

  try {
    const res = await fetch(
      `https://api.nexlev.io/v1/channel?channelUrl=${encodeURIComponent(url)}`,
      { headers: { Authorization: `Bearer ${apiKey}` } }
    );
    if (!res.ok) throw new Error(`NexLev ${res.status}`);
    const d = await res.json();

    return NextResponse.json({
      id: d.channelId || d.id || "",
      title: d.channelTitle || d.title || "Unknown",
      description: d.description || "",
      subscribers: d.subscriberCount || d.subscribers || 0,
      totalViews: d.totalViews || d.views || 0,
      videoCount: d.videoCount || 0,
      monthlyRevenue: d.estimatedMonthlyRevenue || d.monthlyRevenue || 0,
      avgViewsPerVideo: d.avgViewsPerVideo || 0,
      uploadsPerMonth: d.uploadsPerMonth || 0,
      subscriberGrowthRate: d.subscriberGrowthRate || d.growthRate || 0,
      estimatedYearlyRevenue: d.estimatedYearlyRevenue || (d.estimatedMonthlyRevenue || 0) * 12,
      topVideos: (d.topVideos || []).slice(0, 5).map((v: Record<string, unknown>) => ({
        id: v.videoId || v.id || "",
        title: v.title || "",
        views: v.viewCount || v.views || 0,
        publishedAt: v.publishedAt || "",
      })),
      recentGrowth: d.recentGrowth || 0,
      isFaceless: d.isFaceless || false,
      niche: d.niche || d.category || "",
      rpm: d.rpm || 0,
    });
  } catch (err: unknown) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "Error" }, { status: 500 });
  }
}
