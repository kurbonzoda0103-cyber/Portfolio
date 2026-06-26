import { NextRequest, NextResponse } from "next/server";
import Anthropic from "@anthropic-ai/sdk";
const client=new Anthropic({apiKey:process.env.ANTHROPIC_API_KEY});
export async function POST(req:NextRequest){
  const body=await req.json().catch(()=>null);
  if(!body)return NextResponse.json({error:"Invalid request body"},{status:400});
  const{niche,audience,format,language="ru"}=body;
  if(!niche)return NextResponse.json({error:"niche required"},{status:400});
  if(!process.env.ANTHROPIC_API_KEY)return NextResponse.json({error:"ANTHROPIC_API_KEY не задан в .env.local"},{status:500});
  const prompt=`Ты опытный YouTube стратег. Сгенерируй 8 конкретных идей для видео.\n\nНиша: ${niche}\nАудитория: ${audience||"широкая аудитория"}\nФормат: ${format||"длинные видео"}\nЯзык: ${language==="ru"?"русский":"английский"}\n\nОтвет СТРОГО в JSON:\n{"ideas":[{"title":"заголовок до 60 символов","hook":"первые 30 сек","outline":["п1","п2","п3","п4"],"tags":["т1","т2","т3","т4","т5"],"difficulty":"easy|medium|hard","estimatedViews":"1K-10K","whyItWorks":"1-2 предложения"}]}\n\nТолько JSON, без лишнего текста.`;
  try{
    const msg=await client.messages.create({model:"claude-haiku-4-5-20251001",max_tokens:2000,messages:[{role:"user",content:prompt}]});
    const text=msg.content[0].type==="text"?msg.content[0].text:"";
    const m=text.match(/\{[\s\S]*\}/);
    if(!m)throw new Error("Не удалось получить идеи от Claude");
    return NextResponse.json(JSON.parse(m[0]));
  }catch(err:unknown){return NextResponse.json({error:err instanceof Error?err.message:"Error"},{status:500});}
}
