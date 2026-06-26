import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const channel = req.nextUrl.searchParams.get("channel");
  if (!channel) return NextResponse.json({ error: "channel required" }, { status: 400 });

  const apiKey = process.env.NEXLEV_API_KEY;
  if (!apiKey) return NextResponse.json({ error: "NEXLEV_API_KEY не задан" }, { status: 500 });

  try {
    const res = await fetch(
      `https://api.nexlev.io/v1/similar-channels?channelUrl=${encodeURIComponent(channel)}&limit=15`,
      { headers: { Authorization: `Bearer ${apiKey}` } }
    );
    if (!res.ok) throw new Error(`NexLev ${res.status}`);
    const data = await res.json();

    const normalizeChannel = (c: Record<string, unknown>) => ({
      id: c.channelId || c.id || "",
      title: c.channelTitle || c.title || "Unknown",
      subscribers: c.subscriberCount || c.subscribers || 0,
      views: c.totalViews || c.views || 0,
      monthlyRevenue: c.estimatedMonthlyRevenue || c.monthlyRevenue || 0,
      uploadsPerMonth: c.uploadsPerMonth || 0,
      avgViewsPerVideo: c.avgViewsPerVideo || 0,
      engagementRate: c.engagementRate || 0,
      isFaceless: c.isFaceless || false,
      topVideoTitle: c.topVideoTitle || null,
      topVideoViews: c.topVideoViews || null,
    });

    return NextResponse.json({
      anchor: data.anchor ? normalizeChannel(data.anchor) : null,
      competitors: (data.similarChannels || data.competitors || []).map(normalizeChannel),
    });
  } catch (err: unknown) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "Error" }, { status: 500 });
  }
}
