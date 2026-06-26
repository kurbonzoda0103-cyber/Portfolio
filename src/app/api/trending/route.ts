import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const category = req.nextUrl.searchParams.get("category") || "";
  const apiKey = process.env.NEXLEV_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: "NEXLEV_API_KEY не задан" }, { status: 500 });
  }

  try {
    const url = new URL("https://api.nexlev.io/v1/trending");
    if (category) url.searchParams.set("category", category);
    url.searchParams.set("limit", "18");

    const res = await fetch(url.toString(), {
      headers: { Authorization: `Bearer ${apiKey}` },
    });

    if (!res.ok) throw new Error(`NexLev ${res.status}`);
    const data = await res.json();

    const videos = (data.videos || data.results || []).map((v: Record<string, unknown>) => ({
      id: v.videoId || v.id || "",
      title: v.title || "",
      channelTitle: v.channelTitle || v.channel || "",
      viewCount: v.viewCount || v.views || 0,
      likeCount: v.likeCount || v.likes || 0,
      commentCount: v.commentCount || v.comments || 0,
      publishedAt: v.publishedAt || "",
      thumbnailUrl: v.thumbnailUrl || v.thumbnail || "",
      category: v.category || category || "",
      duration: v.duration || "",
    }));

    return NextResponse.json({ videos });
  } catch (err: unknown) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "Error" }, { status: 500 });
  }
}
