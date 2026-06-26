import { NextRequest, NextResponse } from "next/server";

const YT = "https://www.googleapis.com/youtube/v3";

const CATEGORY_IDS: Record<string, string> = {
  technology: "28",
  gaming: "20",
  education: "27",
  entertainment: "24",
  finance: "25",
  health: "26",
  music: "10",
  sports: "17",
};

function parseDuration(iso: string): string {
  const match = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
  if (!match) return "";
  const h = match[1] ? `${match[1]}:` : "";
  const m = match[2]?.padStart(h ? 2 : 1, "0") || "0";
  const s = (match[3] || "0").padStart(2, "0");
  return `${h}${m}:${s}`;
}

export async function GET(req: NextRequest) {
  const category = req.nextUrl.searchParams.get("category") || "";
  const key = process.env.YOUTUBE_API_KEY;
  if (!key) return NextResponse.json({ error: "YOUTUBE_API_KEY не задан" }, { status: 500 });

  const params = new URLSearchParams({
    part: "snippet,statistics,contentDetails",
    chart: "mostPopular",
    maxResults: "18",
    regionCode: "US",
    key,
  });

  const catId = CATEGORY_IDS[category];
  if (catId) params.set("videoCategoryId", catId);

  try {
    const res = await fetch(`${YT}/videos?${params}`);
    if (!res.ok) throw new Error(`YouTube API ${res.status}`);
    const data = await res.json();

    const videos = (data.items || []).map((v: {
      id: string;
      snippet: { title: string; channelTitle: string; publishedAt: string; thumbnails?: { medium?: { url: string } }; categoryId?: string };
      statistics: { viewCount?: string; likeCount?: string; commentCount?: string };
      contentDetails: { duration: string };
    }) => ({
      id: v.id,
      title: v.snippet.title,
      channelTitle: v.snippet.channelTitle,
      viewCount: parseInt(v.statistics.viewCount || "0"),
      likeCount: parseInt(v.statistics.likeCount || "0"),
      commentCount: parseInt(v.statistics.commentCount || "0"),
      publishedAt: v.snippet.publishedAt,
      thumbnailUrl: v.snippet.thumbnails?.medium?.url || "",
      category: category || "trending",
      duration: parseDuration(v.contentDetails.duration),
    }));

    return NextResponse.json({ videos });
  } catch (err: unknown) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "Error" }, { status: 500 });
  }
}
