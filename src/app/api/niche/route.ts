import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q");
  if (!q) return NextResponse.json({ error: "Query required" }, { status: 400 });

  const apiKey = process.env.NEXLEV_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: "NEXLEV_API_KEY не задан в .env.local" }, { status: 500 });
  }

  try {
    const res = await fetch(
      `https://api.nexlev.io/v1/niche-finder/channels?query=${encodeURIComponent(q)}&limit=12`,
      {
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
      }
    );

    if (!res.ok) {
      const err = await res.text();
      throw new Error(`NexLev API error ${res.status}: ${err}`);
    }

    const data = await res.json();

    const channels = (data.channels || data.results || []).map((ch: Record<string, unknown>) => ({
      id: ch.channelId || ch.id || "",
      title: ch.channelTitle || ch.title || "Unknown",
      subscribers: ch.subscriberCount || ch.subscribers || 0,
      views: ch.totalViews || ch.views || 0,
      estimatedMonthlyRevenue: ch.estimatedMonthlyRevenue || ch.monthlyRevenue || 0,
      niche: ch.niche || ch.category || q,
      thumbnailUrl: ch.thumbnailUrl || ch.thumbnail || null,
      outlierScore: ch.outlierScore ?? null,
      uploadsPerMonth: ch.uploadsPerMonth || null,
      qualityRating: ch.qualityRating || null,
      isFaceless: ch.isFaceless || false,
    }));

    const avgRpm =
      channels.reduce((s: number, c: { estimatedMonthlyRevenue: number; views: number }) => {
        const rpm = c.views > 0 ? (c.estimatedMonthlyRevenue / c.views) * 1000 : 0;
        return s + rpm;
      }, 0) / (channels.length || 1);

    return NextResponse.json({
      query: q,
      channels,
      avgRpm,
      totalChannels: data.total || channels.length,
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
