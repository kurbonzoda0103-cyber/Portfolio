import { NextRequest, NextResponse } from "next/server";
const YT="https://www.googleapis.com/youtube/v3";
function extractVideoId(url:string):string|null{
  try{const u=new URL(url);if(u.hostname.includes("youtube.com"))return u.searchParams.get("v");if(u.hostname==="youtu.be")return u.pathname.slice(1).split("?")[0];}catch{}
  if(/^[a-zA-Z0-9_-]{11}$/.test(url))return url;return null;
}
function parseDuration(iso:string){const m=iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);if(!m)return"";const h=m[1]?`${m[1]}:`:"";
return`${h}${(m[2]?.padStart(h?2:1,"0")||"0")}:${(m[3]||"0").padStart(2,"0")}`;}
export async function GET(req:NextRequest){
  const url=req.nextUrl.searchParams.get("url");
  if(!url)return NextResponse.json({error:"url required"},{status:400});
  const videoId=extractVideoId(url);
  if(!videoId)return NextResponse.json({error:"Не удалось извлечь ID видео"},{status:400});
  const key=process.env.YOUTUBE_API_KEY;
  if(!key)return NextResponse.json({error:"YOUTUBE_API_KEY не задан"},{status:500});
  try{
    const[vr,cr]=await Promise.all([fetch(`${YT}/videos?part=snippet,statistics,contentDetails&id=${videoId}&key=${key}`),fetch(`${YT}/commentThreads?part=snippet&videoId=${videoId}&order=relevance&maxResults=10&key=${key}`)]);
    if(!vr.ok)throw new Error(`YouTube API ${vr.status}`);
    const vd=await vr.json();const v=vd.items?.[0];
    if(!v)return NextResponse.json({error:"Видео не найдено"},{status:404});
    const cd=cr.ok?await cr.json():{items:[]};
    const topComments=(cd.items||[]).map((c:{snippet:{topLevelComment:{snippet:{textDisplay:string;likeCount:number}}}})=>({text:c.snippet.topLevelComment.snippet.textDisplay,likeCount:c.snippet.topLevelComment.snippet.likeCount}));
    return NextResponse.json({id:videoId,title:v.snippet.title,channelTitle:v.snippet.channelTitle,description:v.snippet.description||"",viewCount:parseInt(v.statistics.viewCount||"0"),likeCount:parseInt(v.statistics.likeCount||"0"),commentCount:parseInt(v.statistics.commentCount||"0"),publishedAt:v.snippet.publishedAt,duration:parseDuration(v.contentDetails.duration),thumbnailUrl:v.snippet.thumbnails?.maxres?.url||v.snippet.thumbnails?.high?.url||"",tags:v.snippet.tags||[],transcript:null,topComments});
  }catch(err:unknown){return NextResponse.json({error:err instanceof Error?err.message:"Error"},{status:500});}
}
