import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q");
  if (!q) return NextResponse.json({ error: "q required" }, { status: 400 });

  const apiKey = process.env.NEXLEV_API_KEY;
  if (!apiKey) return NextResponse.json({ error: "NEXLEV_API_KEY не задан" }, { status: 500 });

  try {
    const res = await fetch(
      `https://api.nexlev.io/v1/keywords?q=${encodeURIComponent(q)}&limit=10`,
      { headers: { Authorization: `Bearer ${apiKey}` } }
    );
    if (!res.ok) throw new Error(`NexLev ${res.status}`);
    const data = await res.json();

    const keywords = (data.keywords || data.results || []).map((k: Record<string, unknown>) => ({
      keyword: k.keyword || k.term || q,
      searchVolume: k.searchVolume || k.volume || 0,
      competition: k.competition || "medium",
      cpc: k.cpc || 0,
      trend: k.trend || "stable",
      relatedKeywords: k.relatedKeywords || k.related || [],
    }));

    return NextResponse.json({ keywords });
  } catch (err: unknown) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "Error" }, { status: 500 });
  }
}
