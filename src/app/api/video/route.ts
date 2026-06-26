import { NextRequest, NextResponse } from "next/server";

function extractVideoId(url: string): string | null {
  try {
    const u = new URL(url);
    if (u.hostname.includes("youtube.com")) return u.searchParams.get("v");
    if (u.hostname === "youtu.be") return u.pathname.slice(1);
  } catch {
    if (/^[a-zA-Z0-9_-]{11}$/.test(url)) return url;
  }
  return null;
}

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url");
  if (!url) return NextResponse.json({ error: "url required" }, { status: 400 });

  const videoId = extractVideoId(url);
  if (!videoId) return NextResponse.json({ error: "Не удалось извлечь ID видео" }, { status: 400 });

  const apiKey = process.env.NEXLEV_API_KEY;
  if (!apiKey) return NextResponse.json({ error: "NEXLEV_API_KEY не задан" }, { status: 500 });

  try {
    const [statsRes, transcriptRes, commentsRes] = await Promise.allSettled([
      fetch(`https://api.nexlev.io/v1/video/${videoId}`, {
        headers: { Authorization: `Bearer ${apiKey}` },
      }),
      fetch(`https://api.nexlev.io/v1/video/${videoId}/transcript`, {
        headers: { Authorization: `Bearer ${apiKey}` },
      }),
      fetch(`https://api.nexlev.io/v1/video/${videoId}/comments?limit=10`, {
        headers: { Authorization: `Bearer ${apiKey}` },
      }),
    ]);

    if (statsRes.status === "rejected" || !statsRes.value.ok) {
      throw new Error("Не удалось получить данные видео");
    }

    const stats = await statsRes.value.json();
    const transcript =
      transcriptRes.status === "fulfilled" && transcriptRes.value.ok
        ? await transcriptRes.value.json()
        : null;
    const commentsData =
      commentsRes.status === "fulfilled" && commentsRes.value.ok
        ? await commentsRes.value.json()
        : null;

    return NextResponse.json({
      id: videoId,
      title: stats.title || "",
      channelTitle: stats.channelTitle || stats.channel || "",
      description: stats.description || "",
      viewCount: stats.viewCount || stats.views || 0,
      likeCount: stats.likeCount || stats.likes || 0,
      commentCount: stats.commentCount || stats.comments || 0,
      publishedAt: stats.publishedAt || "",
      duration: stats.duration || "",
      thumbnailUrl: stats.thumbnailUrl || stats.thumbnail || "",
      tags: stats.tags || [],
      transcript: transcript?.text || transcript?.transcript || null,
      topComments: (commentsData?.comments || []).slice(0, 10).map((c: Record<string, unknown>) => ({
        text: c.text || c.content || "",
        likeCount: c.likeCount || c.likes || 0,
      })),
    });
  } catch (err: unknown) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "Error" }, { status: 500 });
  }
}
