import { NextRequest, NextResponse } from "next/server";

const YT = "https://www.googleapis.com/youtube/v3";

function extractRef(url: string): { type: "id" | "handle" | "username"; value: string } {
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

export async function GET(req: NextRequest) {
  const channel = req.nextUrl.searchParams.get("channel");
  if (!channel) return NextResponse.json({ error: "channel required" }, { status: 400 });

  const key = process.env.YOUTUBE_API_KEY;
  if (!key) return NextResponse.json({ error: "YOUTUBE_API_KEY не задан" }, { status: 500 });

  try {
    const ref = extractRef(channel);
    const paramKey = ref.type === "id" ? "id" : ref.type === "handle" ? "forHandle" : "forUsername";

    const anchorRes = await fetch(
      `${YT}/channels?part=snippet,statistics&${paramKey}=${encodeURIComponent(ref.value)}&key=${key}`
    );
    if (!anchorRes.ok) throw new Error(`YouTube API ${anchorRes.status}`);
    const anchorData = await anchorRes.json();
    const anchorCh = anchorData.items?.[0];
    if (!anchorCh) return NextResponse.json({ error: "Канал не найден" }, { status: 404 });

    const anchorSubs = parseInt(anchorCh.statistics.subscriberCount || "0");
    const anchorViews = parseInt(anchorCh.statistics.viewCount || "0");

    const keywords = anchorCh.snippet.title.split(" ").slice(0, 2).join(" ");
    const searchRes = await fetch(
      `${YT}/search?part=snippet&type=channel&q=${encodeURIComponent(keywords)}&maxResults=12&key=${key}`
    );
    if (!searchRes.ok) throw new Error(`YouTube API ${searchRes.status}`);
    const searchData = await searchRes.json();

    const ids = (searchData.items || [])
      .map((i: { id: { channelId: string } }) => i.id.channelId)
      .filter((id: string) => id !== anchorCh.id)
      .slice(0, 10)
      .join(",");

    let competitors: {
      id: string; title: string; subscribers: number; views: number;
      monthlyRevenue: number; uploadsPerMonth: number; avgViewsPerVideo: number;
      engagementRate: number; isFaceless: boolean;
    }[] = [];

    if (ids) {
      const cRes = await fetch(`${YT}/channels?part=snippet,statistics&id=${ids}&key=${key}`);
      if (cRes.ok) {
        const cData = await cRes.json();
        competitors = (cData.items || []).map((ch: {
          id: string;
          snippet: { title: string; publishedAt: string };
          statistics: { subscriberCount?: string; viewCount?: string; videoCount?: string };
        }) => {
          const subs = parseInt(ch.statistics.subscriberCount || "0");
          const views = parseInt(ch.statistics.viewCount || "0");
          const videos = parseInt(ch.statistics.videoCount || "1");
          const months = Math.max(1, (Date.now() - new Date(ch.snippet.publishedAt).getTime()) / (1000 * 60 * 60 * 24 * 30));
          return {
            id: ch.id,
            title: ch.snippet.title,
            subscribers: subs,
            views,
            monthlyRevenue: Math.round((views / months / 1000) * 3),
            uploadsPerMonth: Math.round(videos / months),
            avgViewsPerVideo: videos ? Math.round(views / videos) : 0,
            engagementRate: subs ? Math.min((views / videos / subs) * 0.03, 0.2) : 0,
            isFaceless: false,
          };
        });
      }
    }

    return NextResponse.json({
      anchor: {
        id: anchorCh.id,
        title: anchorCh.snippet.title,
        subscribers: anchorSubs,
        views: anchorViews,
        monthlyRevenue: 0,
        uploadsPerMonth: 0,
        avgViewsPerVideo: 0,
        engagementRate: 0,
        isFaceless: false,
      },
      competitors,
    });
  } catch (err: unknown) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "Error" }, { status: 500 });
  }
}
