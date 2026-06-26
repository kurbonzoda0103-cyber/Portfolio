import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null);
  if (!body) return NextResponse.json({ error: "Invalid request body" }, { status: 400 });

  const { niche, audience, format, language = "ru" } = body;
  if (!niche) return NextResponse.json({ error: "niche required" }, { status: 400 });

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) return NextResponse.json({ error: "ANTHROPIC_API_KEY не задан в .env.local" }, { status: 500 });

  const prompt = `Ты опытный YouTube стратег. Сгенерируй 8 конкретных идей для видео.

Ниша: ${niche}
Аудитория: ${audience || "широкая аудитория"}
Формат: ${format || "длинные видео (10-20 минут)"}
Язык контента: ${language === "ru" ? "русский" : "английский"}

Для каждой идеи дай СТРОГО в JSON формате:
{
  "ideas": [
    {
      "title": "конкретный заголовок (до 60 символов)",
      "hook": "первые 30 секунд — что говоришь чтобы зацепить зрителя",
      "outline": ["пункт 1", "пункт 2", "пункт 3", "пункт 4"],
      "tags": ["тег1", "тег2", "тег3", "тег4", "тег5"],
      "difficulty": "easy|medium|hard",
      "estimatedViews": "1K-10K",
      "whyItWorks": "1-2 предложения почему это видео выстрелит"
    }
  ]
}

Важно:
- Заголовки должны быть кликбейтными но честными
- Темы должны быть актуальными прямо сейчас
- Учитывай поисковый спрос
- Только JSON, без лишнего текста`;

  try {
    const message = await client.messages.create({
      model: "claude-haiku-4-5-20251001",
      max_tokens: 2000,
      messages: [{ role: "user", content: prompt }],
    });

    const text = message.content[0].type === "text" ? message.content[0].text : "";

    const jsonMatch = text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error("Не удалось получить идеи от Claude");

    const parsed = JSON.parse(jsonMatch[0]);
    return NextResponse.json(parsed);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Error";
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
